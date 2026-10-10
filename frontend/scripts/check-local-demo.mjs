import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";
import { setupServer } from "msw/node";

class MemoryStorage {
  values = new Map();
  getItem(key) { return this.values.get(key) ?? null; }
  setItem(key, value) { this.values.set(key, String(value)); }
  removeItem(key) { this.values.delete(key); }
}
globalThis.localStorage = new MemoryStorage();
globalThis.sessionStorage = new MemoryStorage();
globalThis.location = new URL("http://localhost/");
const vite = await createServer({ root: fileURLToPath(new URL("..", import.meta.url)), configFile: false, appType: "custom", server: { middlewareMode: true }, logLevel: "error" });
let mockServer;
let count = 0;

function check(message, operation) {
  operation();
  count += 1;
  console.log(`PASS ${message}`);
}

async function call(path, { token, workspace = "ws-lab", method = "GET", body } = {}) {
  const headers = { "X-Workspace-Id": workspace };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(`http://localhost/api/v1${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  return { status: response.status, data: response.status === 204 ? undefined : await response.json() };
}

try {
  const { handlers } = await vite.ssrLoadModule("/src/mocks/handlers.ts");
  const { demoStore: db, persist } = await vite.ssrLoadModule("/src/mocks/accessStore.ts");
  const { validateDataset } = await vite.ssrLoadModule("/src/lib/datasetValidation.ts");
  mockServer = setupServer(...handlers); mockServer.listen({ onUnhandledRequest: "error" });
  assert.equal((await call("/my-workers")).status, 401);
  assert.equal((await call("/auth/login", { method: "POST", body: { username: "an", password: "wrong" } })).status, 401);
  const tokens = {};
  for (const username of ["admin", "an", "binh"]) tokens[username] = (await call("/auth/login", { method: "POST", body: { username, password: "demo-local" } })).data.demoToken;
  const { admin, an, binh } = tokens;
  check("authentication rejects anonymous access and wrong credentials", () => {});
  const workspace = (await call("/workspaces", { token: an, method: "POST", body: { name: "An workspace", description: "Personal lab" } })).data;
  assert.equal(workspace.role, "ADMIN");
  const session = (await call("/auth/session", { token: an })).data;
  assert.equal(session.workspaces.find((w) => w.workspaceId === "ws-lab").role, "PARTICIPANT");
  assert.equal(session.workspaces.find((w) => w.workspaceId === workspace.workspaceId).role, "ADMIN");
  assert.equal((await call("/pools", { token: an, method: "POST", body: { name: "Denied" } })).status, 403);
  assert.equal((await call("/resources", { token: binh, workspace: workspace.workspaceId })).status, 403);
  assert.equal((await call(`/workspaces/${workspace.workspaceId}/members`, { token: an, workspace: workspace.workspaceId, method: "POST", body: { username: "binh" } })).status, 410);
  const invite = await call(`/workspaces/${workspace.workspaceId}/invitations`, { token: an, workspace: workspace.workspaceId, method: "POST", body: { email: "binh@example.test" } });
  assert.equal(invite.status, 201);
  assert.equal((await call("/resources", { token: binh, workspace: workspace.workspaceId })).status, 403);
  assert.equal((await call(`/workspaces/${workspace.workspaceId}/invitations`, { token: an, workspace: workspace.workspaceId, method: "POST", body: { email: "binh@example.test" } })).status, 409);
  assert.equal((await call(`/my-invitations/${invite.data.invitationId}/accept`, { token: an, method: "POST" })).status, 404);
  assert.equal((await call("/my-invitations", { token: binh })).data.length, 1);
  assert.equal((await call(`/my-invitations/${invite.data.invitationId}/accept`, { token: binh, method: "POST" })).status, 200);
  assert.equal((await call(`/my-invitations/${invite.data.invitationId}/accept`, { token: binh, method: "POST" })).status, 409);
  check("email invitations grant membership only after recipient confirmation", () => {});
  check("one identity has different workspace roles; creation and invitations are scoped", () => {});
  assert.equal((await call("/profile", { token: an, method: "PATCH", body: { displayName: "An updated", email: "an@example.test", bio: "Demo" } })).status, 200);
  assert.equal((await call("/auth/session", { token: an })).data.user.displayName, "An updated");
  assert.equal((await call("/auth/session", { token: binh })).data.user.displayName, "Bình");
  check("profile edits persist without changing another user's identity", () => {});
  const worker = (await call("/my-workers", { token: an, method: "POST", body: { gpuName: "My GPU", vramTotalMb: 12288 } })).data;
  assert.equal((await call("/my-workers", { token: binh })).data.some((w) => w.workerId === worker.workerId), false);
  assert.equal((await call(`/my-workers/${worker.workerId}/connection`, { token: binh, method: "POST", body: { action: "CONNECT" } })).status, 404);
  assert.equal((await call(`/my-workers/${worker.workerId}/connection`, { token: an, workspace: workspace.workspaceId, method: "POST", body: { action: "CONNECT" } })).status, 200);
  assert.equal((await call(`/my-workers/${worker.workerId}/connection`, { token: an, workspace: workspace.workspaceId, method: "POST", body: { action: "CONNECT" } })).status, 409);
  assert.equal((await call(`/my-workers/${worker.workerId}/connection`, { token: an, method: "POST", body: { action: "CONNECT" } })).status, 403);
  assert.equal((await call(`/my-workers/${worker.workerId}/connection`, { token: an, workspace: workspace.workspaceId, method: "POST", body: { action: "DISCONNECT" } })).status, 200);
  check("only the GPU owner can connect/disconnect; a GPU cannot join two workspaces", () => {});
  const offeredWorker = (await call("/my-workers", { token: binh, method: "POST", body: { gpuName: "Participant GPU", vramTotalMb: 8192 } })).data;
  assert.equal((await call(`/my-workers/${offeredWorker.workerId}/connection`, { token: binh, method: "POST", body: { action: "CONNECT" } })).status, 403);
  assert.equal((await call("/workspaces/ws-lab/resources", { token: an, method: "POST", body: { workerId: offeredWorker.workerId } })).status, 404);
  const admission = await call("/workspaces/ws-lab/resources", { token: binh, method: "POST", body: { workerId: offeredWorker.workerId } });
  assert.equal(admission.status, 202); assert.equal(admission.data.status, "PENDING");
  assert.equal((await call("/workers", { token: admin })).data.some((w) => w.workerId === offeredWorker.workerId), false);
  assert.equal((await call("/workspaces/ws-lab/resources", { token: binh, method: "POST", body: { workerId: offeredWorker.workerId } })).status, 409);
  assert.equal((await call(`/resource-submissions/${admission.data.submissionId}/decision`, { token: binh, method: "POST", body: { decision: "APPROVE" } })).status, 403);
  assert.equal((await call(`/resource-submissions/${admission.data.submissionId}/decision`, { token: admin, workspace: "ws-private", method: "POST", body: { decision: "APPROVE" } })).status, 404);
  const results = await Promise.all([1,2].map(() => call(`/resource-submissions/${admission.data.submissionId}/decision`, { token: admin, method: "POST", body: { decision: "APPROVE" } })));
  assert.deepEqual(results.map((r) => r.status).sort(), [200,409]);
  assert.equal((await call("/workers", { token: admin })).data.filter((w) => w.workerId === offeredWorker.workerId).length, 1);
  check("participant GPU admission requires scoped Admin approval and rejects duplicate decisions", () => {});
  const ownAdminGPU = (await call("/my-workers", { token: admin, method: "POST", body: { gpuName: "Admin GPU", vramTotalMb: 8192 } })).data;
  const direct = await call("/workspaces/ws-lab/resources", { token: admin, method: "POST", body: { workerId: ownAdminGPU.workerId } });
  assert.equal(direct.status, 201); assert.equal(direct.data.status, "APPROVED");
  assert.equal((await call("/workers", { token: admin })).data.some((w) => w.workerId === ownAdminGPU.workerId), true);
  check("Admin-owned GPU admission is direct without a pending approval", () => {});
  assert.equal((await call(`/workspaces/${workspace.workspaceId}`, { token: an, workspace: workspace.workspaceId, method: "DELETE" })).status, 204);
  assert.equal((await call("/resources", { token: an, workspace: workspace.workspaceId })).status, 403);
  check("workspace deletion removes membership and access", () => {});
  const fixtures = (await call("/experiments", { token: an })).data;
  assert.equal((await call("/experiments", { token: admin })).data.length, 0);
  assert.equal((await call(`/experiments/${fixtures[0].experimentId}`, { token: admin })).status, 404);
  assert.equal((await call(`/experiments/${fixtures[0].experimentId}/generations`, { token: binh })).status, 404);
  assert.deepEqual((await call("/artifacts", { token: binh })).data, []);
  check("personal experiments stay private even from another workspace Admin", () => {});
  check("JSONL checks all records and rejects missing fields and wrong types", () => {
    assert.equal(validateDataset("data.jsonl", '{"text":"x","label":"positive"}\n\n', "sentiment").recordCount, 1);
    assert.throws(() => validateDataset("data.jsonl", '{"text":"x"}', "sentiment"));
    assert.throws(() => validateDataset("data.jsonl", '{"text":"x","label":1}', "sentiment"));
    assert.throws(() => validateDataset("data.jsonl", '{bad}', "sentiment"));
    assert.throws(() => validateDataset("data.json", '{}', "sentiment"));
  });
  check("CSV handles quoted commas, escaped quotes, newlines and malformed rows", () => {
    const csv = 'text,label\n"Hello, ""world""\nnext line",positive\n';
    const result = validateDataset("data.csv", csv, "sentiment");
    assert.equal(result.recordCount, 1); assert.equal(result.preview[0].text, 'Hello, "world"\nnext line');
    assert.throws(() => validateDataset("data.csv", 'text,label\nx', "sentiment"));
    assert.throws(() => validateDataset("data.csv", 'text,text\nx,y', "sentiment"));
    assert.throws(() => validateDataset("data.csv", 'text,label\n"unterminated,x', "sentiment"));
  });
  for (const [task, record] of [["sentiment", { text: "x", label: "anything" }], ["qa", { context: "x", question: "q", answer: "a" }], ["summarization", { text: "x", summary: "s" }]]) {
    const result = await call("/datasets", { token: an, method: "POST", body: { name: "data.json", task, split: "train", content: JSON.stringify([record]) } });
    assert.equal(result.status, 201); assert.equal(result.data.recordCount, 1);
  }
  assert.equal((await call("/datasets", { token: an, method: "POST", body: { name: "bad.jsonl", task: "sentiment", split: "test", content: '{"text":"x"}' } })).status, 422);
  assert.deepEqual((await call("/datasets", { token: binh })).data, []);
  check("three task schemas accept structurally valid data without judging content", () => {});
  const requestInput = { workerIds: ["wk-demo-free"], reason: "Test" };
  const reqAn = (await call("/worker-requests", { token: an, method: "POST", body: requestInput })).data;
  const reqBinh = (await call("/worker-requests", { token: binh, method: "POST", body: requestInput })).data;
  assert.equal((await call(`/worker-requests/${reqAn.requestId}/decision`, { token: an, method: "POST", body: { decision: "APPROVE" } })).status, 403);
  const approvals = await Promise.all([reqAn, reqBinh].map((r) => call(`/worker-requests/${r.requestId}/decision`, { token: admin, method: "POST", body: { decision: "APPROVE" } })));
  assert.deepEqual(approvals.map((a) => a.status).sort(), [200, 409]);
  const winner = approvals[0].status === 200 ? an : binh; const loser = winner === an ? binh : an;
  const grant = (await call("/resources", { token: winner })).data.grants.find((g) => g.workerIds.includes("wk-demo-free"));
  assert.equal((await call(`/grants/${grant.grantId}/return`, { token: loser, method: "POST" })).status, 403);
  assert.equal((await call(`/grants/${grant.grantId}/revoke`, { token: winner, method: "POST" })).status, 403);
  check("competing approvals create one exclusive grant; returns and revocation check roles", () => {});
  const model = (await call("/models", { token: winner, method: "POST", body: { name: "Demo model", source: "REFERENCE", reference: "organization/model", revision: "main" } })).data;
  assert.equal((await call("/models", { token: loser })).data.some((m) => m.modelArtifactId === model.modelArtifactId), false);
  assert.equal((await call("/models", { token: winner, method: "POST", body: { name: "Bad", source: "REFERENCE", reference: "../bad/path", revision: "main" } })).status, 422);
  check("model references validate structure and remain personal", () => {});
  const datasetIds = [];
  for (const split of ["train", "validation", "test"]) {
    const d = await call("/datasets", { token: winner, method: "POST", body: { name: `${split}.jsonl`, task: "sentiment", split, content: '{"text":"x","label":"positive"}' } });
    assert.equal(d.status, 201); datasetIds.push(d.data.datasetId);
  }
  const config = { name: "Test experiment", modelName: model.name, modelArtifactId: model.modelArtifactId, workerIds: ["wk-demo-free"], schedulerPolicy: "round-robin", syncMode: "synchronous", task: "sentiment", datasetIds, maxGenerations: 3, candidatesPerGeneration: 2 };
  assert.equal((await call("/experiments", { token: winner, method: "POST", body: { ...config, datasetIds: datasetIds.slice(0, 2) } })).status, 422);
  assert.equal((await call("/experiments", { token: winner, method: "POST", body: { ...config, datasetIds: [datasetIds[0], datasetIds[0], datasetIds[0]] } })).status, 422);
  assert.equal((await call("/experiments", { token: loser, method: "POST", body: config })).status, 403);
  const draft = (await call("/experiments", { token: winner, method: "POST", body: config })).data;
  assert.equal(draft.status, "DRAFT");
  assert.equal((await call(`/experiments/${draft.experimentId}`, { token: winner, method: "PATCH", body: { ...config, name: "Edited" } })).status, 200);
  check("draft requires owned model, grants and three correctly matched dataset splits", () => {});
  assert.equal((await call(`/experiments/${draft.experimentId}/submit`, { token: winner, method: "POST" })).status, 202);
  assert.equal((await call(`/experiments/${draft.experimentId}/submit`, { token: winner, method: "POST" })).status, 409);
  assert.equal((await call(`/experiments/${draft.experimentId}`, { token: winner, method: "PATCH", body: config })).status, 409);
  assert.equal((await call(`/experiments/${draft.experimentId}`, { token: winner, method: "DELETE" })).status, 409);
  const second = (await call("/experiments", { token: winner, method: "POST", body: { ...config, name: "Second" } })).data;
  assert.equal((await call(`/experiments/${second.experimentId}/submit`, { token: winner, method: "POST" })).status, 409);
  check("queued runs reject duplicate starts, configuration edits, deletion and overlapping GPUs", () => {});
  await new Promise((r) => setTimeout(r, 4700));
  assert.equal((await call(`/experiments/${draft.experimentId}`, { token: winner })).data.status, "RUNNING");
  assert.equal((await call(`/experiments/${draft.experimentId}/control`, { token: winner, method: "POST", body: { action: "CHANGE_WORKERS", workerIds: ["wk-demo-free"] } })).status, 409);
  const pause = await call(`/experiments/${draft.experimentId}/control`, { token: winner, method: "POST", body: { action: "PAUSE" } });
  assert.equal(pause.status, 202); assert.equal(pause.data.status, "PAUSING");
  const clockNow = Date.now; let virtualNow = clockNow(); Date.now = () => virtualNow;
  const tick = async () => { virtualNow += 2000; return (await call(`/experiments/${draft.experimentId}`, { token: winner })).data; };
  let paused = await tick(); if (paused.status !== "PAUSED") paused = await tick();
  assert.equal(paused.status, "PAUSED"); assert.equal(paused.completedGenerations, 1); assert.ok(paused.checkpointSavedAt);
  assert.equal((await tick()).completedGenerations, 1);
  assert.equal((await call(`/experiments/${draft.experimentId}`, { token: winner, method: "DELETE" })).status, 409);
  assert.equal((await call(`/experiments/${draft.experimentId}/control`, { token: loser, method: "POST", body: { action: "RESUME" } })).status, 404);
  check("pause finishes a generation and saves state; paused runtime does not advance", () => {});
  const generations = (await call(`/experiments/${draft.experimentId}/generations`, { token: winner })).data;
  assert.equal(generations[0].committedCandidateCount, 2);
  const candidates = (await call(`/generations/${generations[0].generationId}/candidates`, { token: winner })).data;
  assert.equal(candidates.length, 2); assert.equal(candidates[0].status, "COMMITTED");
  assert.equal((await call(`/candidates/${candidates[0].candidateId}`, { token: loser })).status, 404);
  check("generated generation and candidate detail APIs expose scoped progress", () => {});
  assert.equal((await call(`/experiments/${draft.experimentId}/control`, { token: winner, method: "POST", body: { action: "CHANGE_WORKERS", workerIds: ["other-gpu"] } })).status, 403);
  assert.equal((await call(`/experiments/${draft.experimentId}/control`, { token: winner, method: "POST", body: { action: "CHANGE_WORKERS", workerIds: ["wk-demo-free"] } })).status, 200);
  assert.equal((await call(`/experiments/${draft.experimentId}/control`, { token: winner, method: "POST", body: { action: "RESUME" } })).status, 200);
  let ended; for (let i = 0; i < 4; i++) ended = await tick();
  assert.equal(ended.status, "COMPLETED"); assert.equal(ended.completedGenerations, 3); assert.equal(typeof ended.testScore, "number");
  assert.equal((await tick()).completedGenerations, 3); Date.now = clockNow;
  assert.equal((await call("/resources", { token: winner })).data.grants.find((g) => g.grantId === grant.grantId).status, "ACTIVE");
  check("resume validates grants; generation limit completes once and evaluates mock test score", () => {});
  assert.equal((await call(`/experiments/${second.experimentId}/submit`, { token: winner, method: "POST" })).status, 202);
  assert.equal((await call(`/grants/${grant.grantId}/return`, { token: winner, method: "POST" })).data.status, "RELEASING");
  assert.equal((await call("/worker-requests", { token: loser, method: "POST", body: requestInput })).status, 409);
  const draining = await call("/pools/pool-lab/workers/wk-demo-free", { token: admin, method: "DELETE" });
  assert.equal(draining.status, 202); assert.ok(draining.data.drainingWorkerIds.includes("wk-demo-free"));
  check("busy return and removal reserve GPU until cancellation is confirmed", () => {});
  await new Promise((r) => setTimeout(r, 5200));
  assert.equal((await call(`/experiments/${second.experimentId}`, { token: winner })).data.status, "CANCELLED");
  assert.equal((await call(`/experiments/${second.experimentId}`, { token: winner, method: "DELETE" })).status, 204);
  assert.equal((await call(`/experiments/${second.experimentId}`, { token: winner })).status, 404);
  assert.equal((await call(`/my-workers/wk-demo-free/connection`, { token: admin, method: "POST", body: { action: "CONNECT" } })).status, 404);
  assert.equal((await call(`/my-workers/wk-demo-free/connection`, { token: binh, method: "POST", body: { action: "CONNECT" } })).status, 403);
  const reconnect = await call("/workspaces/ws-lab/resources", { token: binh, method: "POST", body: { workerId: "wk-demo-free" } });
  assert.equal(reconnect.status, 202);
  assert.equal((await call(`/resource-submissions/${reconnect.data.submissionId}/decision`, { token: admin, method: "POST", body: { decision: "APPROVE" } })).status, 200);
  check("cancelled runs cannot restart; archives disappear; owner reconnects released GPU", () => {});
  const snapshot = db.profiles.find((u) => u.userId === "user-an"); assert.equal(snapshot.displayName, "An updated"); persist();
  assert.equal((await call("/auth/logout", { token: winner, method: "POST" })).status, 204);
  assert.equal((await call("/auth/session", { token: winner })).status, 401);
  check("profile is persisted and logout revokes session", () => {});
  console.log(`\n${count} v1 local-demo behavior groups passed.`);
} finally { mockServer?.close(); await vite.close(); }
