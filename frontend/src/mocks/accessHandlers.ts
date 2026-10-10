import { validateDataset } from "../lib/datasetValidation";
import { TASK_FIELDS, type DatasetTask, type DatasetSplit } from "../types/dataset";
import { advanceRuntime, workerTelemetry } from "./runtime";
import { delay, http, HttpResponse, type HttpResponseResolver } from "msw";
import type { ModelRegistration, User } from "../types/access";
import type { CreateExperimentRequest, Experiment } from "../types/experiment";
import { getScenario } from "./scenario";
import { audit, busyWorkers, cancelSimulation, currentUser, demoStore as db, finalizeReleases, isBusy, membersFor, newId, now, ownedWorkerIds, persist, withDemoStore, workspacesFor } from "./accessStore";

class DemoError extends Error {
  readonly status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}
const fail = (status: number, message: string): never => { throw new DemoError(status, message); };

export function scopeFor(request: Request, admin = false, targetWorkspaceId?: string) {
  const user = currentUser(request);
  if (!user) return fail(401, "Please sign in. This is a local demo session.");
  const workspaceId = targetWorkspaceId ?? request.headers.get("X-Workspace-Id") ?? "";
  const membership = db.memberships.find((item) => item.userId === user.userId && item.workspaceId === workspaceId);
  if (!membership) return fail(403, "You do not belong to this workspace.");
  if (admin && membership.role !== "ADMIN") return fail(403, "This action requires the workspace Admin.");
  return { user, workspaceId, role: membership.role };
}

export function canReadExperiment(request: Request, experimentId: string) {
  const { user, workspaceId } = scopeFor(request);
  return db.experiments.find((item) => item.experimentId === experimentId && item.workspaceId === workspaceId && !item.archivedAt && item.ownerUserId === user.userId);
}

export function readableExperimentIds(request: Request) {
  const { user, workspaceId } = scopeFor(request);
  return new Set(db.experiments.filter((item) => item.workspaceId === workspaceId && !item.archivedAt && item.ownerUserId === user.userId).map((item) => item.experimentId));
}

export function demoResolver(handler: (request: Request, params: Record<string, string | readonly string[] | undefined>) => Response | Promise<Response>): HttpResponseResolver {
  return async ({ request, params }) => {
    try {
      await delay(150);
      if (getScenario() === "stale") return HttpResponse.error();
      return await withDemoStore(() => { advanceRuntime(); return handler(request, params); });
    } catch (error) {
      if (error instanceof DemoError) return HttpResponse.json({ message: error.message }, { status: error.status });
      if (error instanceof SyntaxError) return HttpResponse.json({ message: "Invalid JSON." }, { status: 400 });
      throw error;
    }
  };
}

async function body(request: Request): Promise<Record<string, unknown>> {
  const value: unknown = await request.json();
  if (!value || typeof value !== "object" || Array.isArray(value)) return fail(422, "Expected a JSON object.");
  return value as Record<string, unknown>;
}

function text(value: unknown, label: string, max = 160) {
  if (typeof value !== "string" || value.trim().length < 1 || value.trim().length > max) return fail(422, `${label} is required (up to ${max} characters).`);
  return value.trim();
}

function ids(value: unknown) {
  if (!Array.isArray(value) || !value.length || value.some((id) => typeof id !== "string")) return fail(422, "Select at least one worker.");
  if (new Set(value).size !== value.length) return fail(422, "Worker IDs must be unique.");
  return value as string[];
}

function poolFor(poolId: unknown, workspaceId: string) {
  return db.pools.find((pool) => pool.poolId === poolId && pool.workspaceId === workspaceId) ?? fail(404, "Pool not found.");
}

function validateConfig(input: Record<string, unknown>): CreateExperimentRequest {
  if (input.task === undefined) return fail(422, "Task and train/validation/test datasets are required.");
  const name = text(input.name, "Experiment name");
  if (name.length < 3) return fail(422, "Experiment name needs at least 3 characters.");
  if (input.schedulerPolicy !== "capacity-weighted" && input.schedulerPolicy !== "round-robin") return fail(422, "Unknown scheduling policy.");
  if (input.syncMode !== "synchronous" && input.syncMode !== "asynchronous") return fail(422, "Unknown sync mode.");
  const extras: Partial<CreateExperimentRequest> = {};
  if (input.task !== undefined) {
    if (typeof input.task !== "string" || !Object.hasOwn(TASK_FIELDS, input.task)) return fail(422, "Choose a supported task.");
    if (!Number.isInteger(input.maxGenerations) || Number(input.maxGenerations) < 1 || Number(input.maxGenerations) > 1000) return fail(422, "Generations must be 1–1000.");
    if (!Number.isInteger(input.candidatesPerGeneration) || Number(input.candidatesPerGeneration) < 1 || Number(input.candidatesPerGeneration) > 256) return fail(422, "Candidates must be 1–256.");
    if (!Array.isArray(input.datasetIds) || input.datasetIds.length !== 3 || input.datasetIds.some((id) => typeof id !== "string")) return fail(422, "Select train, validation and test datasets.");
    Object.assign(extras, { task: input.task, maxGenerations: input.maxGenerations, candidatesPerGeneration: input.candidatesPerGeneration, datasetIds: input.datasetIds });
  }
  return { ...extras, name, modelName: text(input.modelName, "Model name"), schedulerPolicy: input.schedulerPolicy, syncMode: input.syncMode, workerIds: ids(input.workerIds), modelArtifactId: text(input.modelArtifactId, "Model artifact") };
}

function validateSelection(input: CreateExperimentRequest, user: User, workspaceId: string) {
  const model = db.models.find((item) => item.modelArtifactId === input.modelArtifactId && item.workspaceId === workspaceId && item.ownerUserId === user.userId);
  if (!model) return fail(403, "Select your model registered in this workspace.");
  if (model.source !== "REFERENCE") return fail(422, "Use a repository model reference.");
  if (input.task && input.task !== "Countdown") {
    const datasets = (input.datasetIds ?? []).map((id) => db.datasets.find((d) => d.datasetId === id && d.ownerUserId === user.userId && d.workspaceId === workspaceId && d.task === input.task));
    if (datasets.length !== 3 || datasets.some((d) => !d) || new Set(datasets.map((d) => d?.split)).size !== 3) return fail(422, "Require your validated train, validation and test datasets for this task.");
  }
  const owned = ownedWorkerIds(user.userId, workspaceId);
  if (input.workerIds?.some((id) => !owned.includes(id) || !db.pools.some((pool) => pool.workspaceId === workspaceId && pool.workerIds.includes(id) && !pool.drainingWorkerIds.includes(id)))) return fail(403, "You can only select your active, non-draining worker grants.");
  return model;
}


function addResource(workerId: string, workspaceId: string) {
  if (db.pools.some((p) => p.workerIds.includes(workerId)) || busyWorkers().has(workerId) || db.grants.some((g) => g.status !== "RELEASED" && g.workerIds.includes(workerId))) return fail(409, "Worker is connected, allocated or busy.");
  let pool = db.pools.find((p) => p.workspaceId === workspaceId);
  if (!pool) { pool = { poolId: newId("resources"), workspaceId, name: "Resources", workerIds: [], drainingWorkerIds: [] }; db.pools.push(pool); }
  pool.workerIds.push(workerId);
}
const emailFor = (user: User) => (user.email || `${user.username}@example.test`).trim().toLowerCase();

export const accessHandlers = [
  http.post("/api/v1/workspaces/:workspaceId/invitations", demoResolver(async (request, params) => {
    const { user, workspaceId } = scopeFor(request, true, String(params.workspaceId));
    const email = text((await body(request)).email, "Email", 254).toLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return fail(422, "Invalid email address.");
    if (membersFor(workspaceId).some((m) => emailFor(m.user) === email)) return fail(409, "Account is already a member.");
    if (db.invitations.some((i) => i.workspaceId === workspaceId && i.email === email && i.status === "PENDING")) return fail(409, "Invitation is already pending.");
    const workspaceName = db.workspaces.find((w) => w.workspaceId === workspaceId)!.name;
    const invitation = { invitationId: newId("invite"), workspaceId, workspaceName, email, status: "PENDING" as const, createdAt: now() };
    db.invitations.push(invitation); audit(user, workspaceId, "INVITATION_CREATED", invitation.invitationId);
    return HttpResponse.json(invitation, { status: 201 });
  })),
  http.get("/api/v1/my-invitations", demoResolver((request) => {
    const user = currentUser(request) ?? fail(401, "Please sign in.");
    return HttpResponse.json(db.invitations.filter((i) => i.email === emailFor(user) && db.workspaces.some((w) => w.workspaceId === i.workspaceId)));
  })),
  http.post("/api/v1/my-invitations/:invitationId/accept", demoResolver((request, params) => {
    const user = currentUser(request) ?? fail(401, "Please sign in.");
    const i = db.invitations.find((i) => i.invitationId === params.invitationId && i.email === emailFor(user)) ?? fail(404, "Invitation not found.");
    if (i.status !== "PENDING") return fail(409, "Invitation is already accepted.");
    if (!db.workspaces.some((w) => w.workspaceId === i.workspaceId)) return fail(404, "Workspace not found.");
    if (!db.memberships.some((m) => m.userId === user.userId && m.workspaceId === i.workspaceId)) db.memberships.push({ userId: user.userId, workspaceId: i.workspaceId, role: "PARTICIPANT" });
    i.status = "ACCEPTED"; audit(user, i.workspaceId, "INVITATION_ACCEPTED", i.invitationId);
    return HttpResponse.json(i);
  })),
  http.get("/api/v1/my-resource-submissions", demoResolver((request) => {
    const user = currentUser(request) ?? fail(401, "Please sign in.");
    return HttpResponse.json(db.submissions.filter((s) => s.ownerUserId === user.userId && db.workspaces.some((w) => w.workspaceId === s.workspaceId)));
  })),
  http.post("/api/v1/workspaces/:workspaceId/resources", demoResolver(async (request, params) => {
    const { user, workspaceId, role } = scopeFor(request, false, String(params.workspaceId));
    const workerId = text((await body(request)).workerId, "Worker ID");
    const worker = db.workers.find((w) => w.workerId === workerId && w.ownerUserId === user.userId) ?? fail(404, "Owned Worker not found.");
    if (db.pools.some((p) => p.workerIds.includes(workerId))) return fail(409, "Worker is already connected.");
    if (db.submissions.some((s) => s.workerId === workerId && s.status === "PENDING")) return fail(409, "Worker admission is already pending.");
    const submission = { submissionId: newId("admission"), workspaceId, workerId, ownerUserId: user.userId, ownerName: user.displayName, gpuName: worker.profile.gpuName, status: role === "ADMIN" ? "APPROVED" as const : "PENDING" as const, createdAt: now() };
    if (role === "ADMIN") addResource(workerId, workspaceId);
    db.submissions.push(submission); audit(user, workspaceId, role === "ADMIN" ? "RESOURCE_ADDED" : "RESOURCE_ADMISSION_REQUESTED", workerId);
    return HttpResponse.json(submission, { status: role === "ADMIN" ? 201 : 202 });
  })),
  http.post("/api/v1/resource-submissions/:submissionId/decision", demoResolver(async (request, params) => {
    const { user, workspaceId } = scopeFor(request, true);
    const s = db.submissions.find((s) => s.submissionId === params.submissionId && s.workspaceId === workspaceId) ?? fail(404, "Admission request not found.");
    if (s.status !== "PENDING") return fail(409, "Admission request has already been decided.");
    const decision = (await body(request)).decision;
    if (decision !== "APPROVE" && decision !== "REJECT") return fail(422, "Invalid decision.");
    if (decision === "APPROVE") {
      if (!db.memberships.some((m) => m.userId === s.ownerUserId && m.workspaceId === workspaceId) || !db.workers.some((w) => w.workerId === s.workerId && w.ownerUserId === s.ownerUserId)) return fail(409, "Worker owner is no longer eligible.");
      addResource(s.workerId, workspaceId);
    }
    s.status = decision === "APPROVE" ? "APPROVED" : "REJECTED";
    audit(user, workspaceId, `RESOURCE_ADMISSION_${s.status}`, s.workerId); return HttpResponse.json(s);
  })),
  http.patch("/api/v1/profile", demoResolver(async (request) => {
    const user = currentUser(request) ?? fail(401, "Please sign in.");
    const input = await body(request);
    user.displayName = text(input.displayName, "Display name");
    user.email = typeof input.email === "string" ? input.email.slice(0, 254) : "";
    user.bio = typeof input.bio === "string" ? input.bio.slice(0, 1000) : "";
    persist(); return HttpResponse.json(user);
  })),
  http.delete("/api/v1/workspaces/:workspaceId", demoResolver((request, params) => {
    const { workspaceId, user } = scopeFor(request, true);
    if (params.workspaceId !== workspaceId) return fail(404, "Workspace not found.");
    if (db.experiments.some((e) => e.workspaceId === workspaceId && (isBusy(e) || e.status === "PAUSED"))) return fail(409, "Cancel active or paused experiments before deleting the workspace.");
    if (db.grants.some((g) => g.workspaceId === workspaceId && g.status !== "RELEASED")) return fail(409, "Release all grants first.");
    db.workspaces = db.workspaces.filter((w) => w.workspaceId !== workspaceId);
    db.memberships = db.memberships.filter((m) => m.workspaceId !== workspaceId);
    db.pools = db.pools.filter((p) => p.workspaceId !== workspaceId);
    db.submissions = db.submissions.filter((s) => s.workspaceId !== workspaceId);
    db.invitations = db.invitations.filter((i) => i.workspaceId !== workspaceId);
    audit(user, workspaceId, "WORKSPACE_DELETED", workspaceId);
    return new HttpResponse(null, { status: 204 });
  })),
  http.get("/api/v1/my-workers", demoResolver((request) => {
    const user = currentUser(request) ?? fail(401, "Please sign in.");
    return HttpResponse.json(db.workers.filter((w) => w.ownerUserId === user.userId).map((w) => ({ ...workerTelemetry(w), workspaceId: db.pools.find((p) => p.workerIds.includes(w.workerId))?.workspaceId })));
  })),
  http.post("/api/v1/my-workers", demoResolver(async (request) => {
    const user = currentUser(request) ?? fail(401, "Please sign in."); const input = await body(request);
    const vram = Number(input.vramTotalMb);
    if (!Number.isInteger(vram) || vram < 1024 || vram > 1048576) return fail(422, "VRAM must be 1024–1048576 MiB.");
    const worker = { workerId: newId("gpu"), ownerUserId: user.userId, profile: { gpuName: text(input.gpuName, "GPU name"), vramTotalMb: vram }, status: "ONLINE" as const, admissionStatus: "ADMITTED" as const, lastHeartbeatAt: now() };
    db.workers.push(worker); persist(); return HttpResponse.json(worker, { status: 201 });
  })),
  http.post("/api/v1/my-workers/:workerId/connection", demoResolver(async (request, params) => {
    const input = await body(request); const { user, workspaceId } = scopeFor(request, false, typeof input.workspaceId === "string" ? input.workspaceId : undefined);
    const worker = db.workers.find((w) => w.workerId === params.workerId && w.ownerUserId === user.userId) ?? fail(404, "Your Worker was not found.");
    const existing = db.pools.find((p) => p.workerIds.includes(worker.workerId));
    if (input.action === "CONNECT") {
      if (scopeFor(request, false, workspaceId).role !== "ADMIN") return fail(403, "Resource admission requires workspace Admin approval.");
      if (existing) return fail(409, "Disconnect the existing workspace first.");
      let pool = db.pools.find((p) => p.workspaceId === workspaceId);
      if (!pool) { pool = { poolId: newId("pool"), workspaceId, name: "Shared GPU Pool", workerIds: [], drainingWorkerIds: [] }; db.pools.push(pool); }
      pool.workerIds.push(worker.workerId); worker.status = "ONLINE";
    } else if (input.action === "DISCONNECT") {
      if (!existing || existing.workspaceId !== workspaceId) return fail(404, "Worker is not connected to this workspace.");
      if (busyWorkers().has(worker.workerId) || db.grants.some((g) => g.status !== "RELEASED" && g.workerIds.includes(worker.workerId))) return fail(409, "Return or revoke the allocation and stop its work before disconnecting.");
      existing.workerIds = existing.workerIds.filter((id) => id !== worker.workerId);
    } else return fail(422, "Unknown connection action.");
    audit(user, workspaceId, "WORKER_CONNECTION_CHANGED", worker.workerId); return HttpResponse.json(worker);
  })),
  http.get("/api/v1/datasets", demoResolver((request) => {
    const { user, workspaceId } = scopeFor(request);
    return HttpResponse.json(db.datasets.filter((d) => d.ownerUserId === user.userId && d.workspaceId === workspaceId));
  })),
  http.post("/api/v1/datasets", demoResolver(async (request) => {
    const { user, workspaceId } = scopeFor(request); const input = await body(request);
    if (typeof input.task !== "string" || !Object.hasOwn(TASK_FIELDS, input.task) || !["train", "validation", "test"].includes(String(input.split))) return fail(422, "Unknown task or split.");
    const name = text(input.name, "Filename", 255);
    if (typeof input.content !== "string") return fail(422, "File content is required.");
    try {
      const metadata = validateDataset(name, input.content, input.task as DatasetTask);
      const dataset = { ...metadata, datasetId: newId("dataset"), workspaceId, ownerUserId: user.userId, name, task: input.task as DatasetTask, split: input.split as DatasetSplit };
      db.datasets.push(dataset); persist(); return HttpResponse.json(dataset, { status: 201 });
    } catch (error) { return fail(422, error instanceof Error ? error.message : "Invalid dataset."); }
  })),
  http.post("/api/v1/experiments/:experimentId/control", demoResolver(async (request, params) => {
    const { user, workspaceId } = scopeFor(request);
    const e = canReadExperiment(request, String(params.experimentId)) ?? fail(404, "Experiment not found.");
    if (e.ownerUserId !== user.userId) return fail(403, "Only the owner can control this experiment.");
    const input = await body(request);
    if (input.action === "PAUSE") {
      if (e.status !== "RUNNING" || e.cancelRequested || !e.maxGenerations) return fail(409, "Only a configured running experiment can pause.");
      e.status = "PAUSING";
    } else if (input.action === "RESUME") {
      if (e.status !== "PAUSED") return fail(409, "Experiment must be paused.");
      validateSelection(e, user, workspaceId);
      if (e.workerIds?.some((id) => { const w = db.workers.find((w) => w.workerId === id); return !w || w.status !== "ONLINE" || !["ADMITTED", "ADMITTED_LIMITED"].includes(w.admissionStatus) || busyWorkers().has(id); })) return fail(409, "A worker is busy, offline or not admitted.");
      e.status = "RUNNING"; e.mockTickAt = Date.now();
    } else if (input.action === "CHANGE_WORKERS") {
      if (e.status !== "PAUSED") return fail(409, "Pause at a generation boundary before changing Workers.");
      const workerIds = ids(input.workerIds); validateSelection({ ...e, workerIds }, user, workspaceId);
      e.workerIds = workerIds;
    } else return fail(422, "Unknown control action.");
    audit(user, workspaceId, `EXPERIMENT_${String(input.action)}`, e.experimentId); return HttpResponse.json(e, { status: e.status === "PAUSING" ? 202 : 200 });
  })),
  http.post("/api/v1/auth/login", demoResolver(async (request) => {
    const input = await body(request);
    const user = db.profiles.find((item) => item.username === String(input.username).trim().toLowerCase());
    // Public, fake credentials. Never use this handler for production authentication.
    if (!user || input.password !== "demo-local") return fail(401, "Invalid demo username or password.");
    const token = newId("demo-session");
    db.sessions.push({ token, userId: user.userId, expiresAt: Date.now() + 8 * 60 * 60 * 1000 });
    persist();
    return HttpResponse.json({ user, workspaces: workspacesFor(user), demoToken: token });
  })),
  http.get("/api/v1/auth/session", demoResolver((request) => {
    const user = currentUser(request) ?? fail(401, "Please sign in.");
    return HttpResponse.json({ user, workspaces: workspacesFor(user) });
  })),
  http.post("/api/v1/auth/logout", demoResolver((request) => {
    const token = request.headers.get("Authorization")?.replace(/^Bearer /, "");
    db.sessions = db.sessions.filter((session) => session.token !== token);
    persist();
    return new HttpResponse(null, { status: 204 });
  })),
  http.get("/api/v1/workspaces", demoResolver((request) => {
    const user = currentUser(request) ?? fail(401, "Please sign in.");
    return HttpResponse.json(workspacesFor(user));
  })),
  http.post("/api/v1/workspaces", demoResolver(async (request) => {
    const user = currentUser(request) ?? fail(401, "Please sign in.");

    const input = await body(request);
    const name = text(input.name, "Workspace name");
    const workspace = { workspaceId: newId("ws"), name, description: typeof input.description === "string" ? input.description.slice(0, 1000) : "", creatorUserId: user.userId };
    db.workspaces.push(workspace);
    db.memberships.push({ userId: user.userId, workspaceId: workspace.workspaceId, role: "ADMIN" });
    audit(user, workspace.workspaceId, "WORKSPACE_CREATED", workspace.workspaceId);
    return HttpResponse.json({ ...workspace, role: "ADMIN" }, { status: 201 });
  })),
  http.post("/api/v1/workspaces/:workspaceId/members", demoResolver((request, params) => {
    scopeFor(request, true, String(params.workspaceId));
    return fail(410, "Direct membership creation is retired. Use an email invitation and recipient confirmation.");
  })),
  http.get("/api/v1/resources", demoResolver((request) => {
    const { user, workspaceId, role } = scopeFor(request);
    finalizeReleases();
    const workerIds = db.pools.filter((pool) => pool.workspaceId === workspaceId).flatMap((pool) => pool.workerIds);
    return HttpResponse.json({
      submissions: db.submissions.filter((s) => s.workspaceId === workspaceId && (role === "ADMIN" || s.ownerUserId === user.userId)),
      invitations: role === "ADMIN" ? db.invitations.filter((i) => i.workspaceId === workspaceId) : [],
      pools: db.pools.filter((pool) => pool.workspaceId === workspaceId),
      grants: db.grants.filter((grant) => grant.workspaceId === workspaceId),
      requests: db.requests.filter((item) => item.workspaceId === workspaceId && (role === "ADMIN" || item.userId === user.userId)),
      members: membersFor(workspaceId),
      busyWorkerIds: [...busyWorkers()].filter((id) => workerIds.includes(id)),
      reservedWorkerIds: db.grants.filter((grant) => grant.workspaceId === workspaceId && grant.status !== "RELEASED").flatMap((grant) => grant.workerIds),
    });
  })),
  http.post("/api/v1/pools", demoResolver(async (request) => {
    const { user, workspaceId } = scopeFor(request, true);
    const pool = { poolId: newId("pool"), workspaceId, name: text((await body(request)).name, "Pool name"), workerIds: [], drainingWorkerIds: [] };
    db.pools.push(pool);
    audit(user, workspaceId, "POOL_CREATED", pool.poolId);
    return HttpResponse.json(pool, { status: 201 });
  })),
  http.get("/api/v1/worker-registry", demoResolver((request) => {
    const { user } = scopeFor(request, true);
    return HttpResponse.json(db.workers.filter((worker) => worker.ownerUserId === user.userId).filter((worker) => !db.pools.some((pool) => pool.workerIds.includes(worker.workerId))));
  })),
  http.post("/api/v1/pools/:poolId/workers", demoResolver(async (request, params) => {
    const { user, workspaceId } = scopeFor(request, true);
    const pool = poolFor(params.poolId, workspaceId);
    const workerId = text((await body(request)).workerId, "Worker ID");
    if (!db.workers.some((worker) => worker.workerId === workerId && worker.ownerUserId === user.userId)) return fail(403, "Only the GPU owner can connect this Worker. Use the Worker tab.");
    if (db.pools.some((item) => item.workerIds.includes(workerId))) return fail(409, "Worker already belongs to a pool.");
    if (db.grants.some((grant) => grant.status !== "RELEASED" && grant.workerIds.includes(workerId)) || busyWorkers().has(workerId)) return fail(409, "Worker is still reserved or busy.");
    pool.workerIds.push(workerId);
    audit(user, workspaceId, "WORKER_ADDED_TO_POOL", workerId);
    return HttpResponse.json(pool);
  })),
  http.post("/api/v1/demo/workers", demoResolver(async (request) => {
    const { user, workspaceId } = scopeFor(request, true);
    const input = await body(request);
    const pool = poolFor(input.poolId, workspaceId);
    const workerId = text(input.workerId, "Worker ID", 80);
    if (!/^[a-zA-Z0-9_-]+$/.test(workerId)) return fail(422, "Use letters, digits, underscores or hyphens for Worker ID.");
    if (db.workers.some((worker) => worker.workerId === workerId)) return fail(409, "Worker ID already exists.");
    if (typeof input.vramTotalMb !== "number" || !Number.isFinite(input.vramTotalMb) || input.vramTotalMb < 1024 || input.vramTotalMb > 1048576) return fail(422, "VRAM must be between 1024 and 1048576 MiB.");
    const worker = { workerId, ownerUserId: user.userId, status: "ONLINE" as const, admissionStatus: "ADMITTED" as const, profile: { gpuName: text(input.gpuName, "GPU name"), vramTotalMb: input.vramTotalMb }, lastHeartbeatAt: now() };
    db.workers.push(worker);
    pool.workerIds.push(workerId);
    audit(user, workspaceId, "DEMO_WORKER_REGISTERED", workerId);
    return HttpResponse.json(worker, { status: 201 });
  })),
  http.delete("/api/v1/pools/:poolId/workers/:workerId", demoResolver((request, params) => {
    const { user, workspaceId } = scopeFor(request, true);
    const pool = poolFor(params.poolId, workspaceId);
    const workerId = String(params.workerId);
    if (!pool.workerIds.includes(workerId)) return fail(404, "Worker not in this pool.");
    if (pool.drainingWorkerIds.includes(workerId)) return fail(409, "Removal is already pending.");
    pool.drainingWorkerIds.push(workerId);
    const affected = new Set([workerId]);
    for (const grant of db.grants.filter((grant) => grant.status !== "RELEASED" && grant.workerIds.includes(workerId))) {
      grant.status = "RELEASING";
      grant.requestedBy = "ADMIN";
      grant.workerIds.forEach((id) => affected.add(id));
    }
    db.experiments.filter((experiment) => isBusy(experiment) && experiment.workerIds?.some((id) => affected.has(id))).forEach(cancelSimulation);
    finalizeReleases();
    audit(user, workspaceId, "POOL_WORKER_REMOVAL_REQUESTED", workerId);
    return HttpResponse.json(pool, { status: pool.drainingWorkerIds.includes(workerId) ? 202 : 200 });
  })),
  http.post("/api/v1/worker-requests", demoResolver(async (request) => {
    const { user, workspaceId } = scopeFor(request);
    const input = await body(request);
    const workerIds = ids(input.workerIds);
    const pool = input.poolId === undefined ? db.pools.find((p) => p.workspaceId === workspaceId && p.workerIds.includes(workerIds[0])) ?? fail(422, "Worker is not a workspace resource.") : poolFor(input.poolId, workspaceId);
    if (workerIds.some((id) => !db.pools.some((p) => p.workspaceId === workspaceId && p.workerIds.includes(id) && !p.drainingWorkerIds.includes(id)))) return fail(422, "Choose available workspace resources.");
    if (db.requests.some((item) => item.userId === user.userId && item.workspaceId === workspaceId && item.status === "PENDING" && item.workerIds.some((id) => workerIds.includes(id)))) return fail(409, "An overlapping request is already pending.");
    if (db.grants.some((grant) => grant.status !== "RELEASED" && grant.workerIds.some((id) => workerIds.includes(id)))) return fail(409, "These workers are already reserved. Request free workers.");
    const item = { requestId: newId("request"), workspaceId, poolId: pool.poolId, userId: user.userId, workerIds, reason: text(input.reason, "Request reason", 1000), status: "PENDING" as const, createdAt: now() };
    db.requests.unshift(item);
    audit(user, workspaceId, "WORKERS_REQUESTED", item.requestId);
    return HttpResponse.json(item, { status: 201 });
  })),
  http.post("/api/v1/worker-requests/:requestId/decision", demoResolver(async (request, params) => {
    const { user, workspaceId } = scopeFor(request, true);
    const item = db.requests.find((item) => item.requestId === params.requestId && item.workspaceId === workspaceId) ?? fail(404, "Request not found.");
    if (item.status !== "PENDING") return fail(409, "Request has already been decided.");
    const { decision } = await body(request);
    if (decision !== "APPROVE" && decision !== "REJECT") return fail(422, "Unknown decision.");
    if (decision === "APPROVE") {
      poolFor(item.poolId, workspaceId);
      if (item.workerIds.some((id) => !db.pools.some((p) => p.workspaceId === workspaceId && p.workerIds.includes(id) && !p.drainingWorkerIds.includes(id)))) return fail(409, "Some Workers are no longer available in Resources.");
      if (!db.memberships.some((membership) => membership.userId === item.userId && membership.workspaceId === workspaceId)) return fail(409, "Requester is no longer a member.");
      if (db.grants.some((grant) => grant.status !== "RELEASED" && grant.workerIds.some((id) => item.workerIds.includes(id))) || item.workerIds.some((id) => busyWorkers().has(id))) return fail(409, "Some workers are reserved or busy. No partial grant was created.");
      db.grants.push({ grantId: newId("grant"), workspaceId, poolId: item.poolId, userId: item.userId, workerIds: [...item.workerIds], status: "ACTIVE", createdAt: now() });
    }
    item.status = decision === "APPROVE" ? "APPROVED" : "REJECTED";
    audit(user, workspaceId, `WORKER_REQUEST_${item.status}`, item.requestId);
    return HttpResponse.json(item);
  })),
  http.post("/api/v1/grants/:grantId/:action", demoResolver((request, params) => {
    const { user, workspaceId, role } = scopeFor(request);
    const grant = db.grants.find((grant) => grant.grantId === params.grantId && grant.workspaceId === workspaceId) ?? fail(404, "Grant not found.");
    if (params.action === "revoke" && role !== "ADMIN") return fail(403, "Only Admin can revoke grants.");
    if (params.action === "return" && grant.userId !== user.userId) return fail(403, "You can only return your own grant.");
    if (params.action !== "return" && params.action !== "revoke") return fail(404, "Unknown grant action.");
    if (grant.status !== "ACTIVE") return fail(409, "This grant is already releasing or released.");
    grant.status = "RELEASING";
    grant.requestedBy = params.action === "revoke" ? "ADMIN" : "PARTICIPANT";
    db.experiments.filter((experiment) => isBusy(experiment) && experiment.workerIds?.some((id) => grant.workerIds.includes(id))).forEach(cancelSimulation);
    finalizeReleases();
    audit(user, workspaceId, params.action === "revoke" ? "GRANT_REVOCATION_REQUESTED" : "GRANT_RETURN_REQUESTED", grant.grantId);
    return HttpResponse.json(grant, { status: grant.status === "RELEASING" ? 202 : 200 });
  })),
  http.get("/api/v1/models", demoResolver((request) => {
    const { user, workspaceId } = scopeFor(request);
    return HttpResponse.json(db.models.filter((model) => model.workspaceId === workspaceId && model.ownerUserId === user.userId));
  })),
  http.post("/api/v1/models", demoResolver(async (request) => {
    const { user, workspaceId } = scopeFor(request);
    const input = await body(request);
    const name = text(input.name, "Model name");
    if (input.source !== "REFERENCE" && input.source !== "UPLOAD_METADATA") return fail(422, "Unknown model source.");
    let reference: string | undefined;
    let revision: string | undefined;
    let files: { name: string; sizeBytes: number }[] | undefined;
    if (input.source === "REFERENCE") {
      reference = text(input.reference, "Repository reference");
      revision = text(input.revision, "Revision");
      if (!/^[\w.-]+\/[\w.-]+$/.test(reference)) return fail(422, "Use a repository ID such as organization/model.");
    } else {
      if (!Array.isArray(input.files) || !input.files.length || input.files.length > 100) return fail(422, "Select 1–100 model files. This demo registers metadata only.");
      files = input.files.map((file: unknown) => {
        if (!file || typeof file !== "object" || !("name" in file) || !("sizeBytes" in file)) return fail(422, "Invalid file metadata.");
        const fileName = text(file.name, "Filename", 255);
        if (/[\\/]/.test(fileName) || !/\.(safetensors|json|model|txt)$/i.test(fileName) || typeof file.sizeBytes !== "number" || !Number.isSafeInteger(file.sizeBytes) || file.sizeBytes <= 0) return fail(422, "Use non-empty safetensors, JSON, tokenizer .model or .txt files.");
        return { name: fileName, sizeBytes: file.sizeBytes };
      });
      if (new Set(files.map((file) => file.name)).size !== files.length) return fail(422, "Filenames must be unique.");
    }
    const model: ModelRegistration = { modelArtifactId: newId("model"), workspaceId, ownerUserId: user.userId, name, source: input.source, reference, revision, files, status: "REGISTERED", createdAt: now() };
    db.models.push(model);
    audit(user, workspaceId, "MODEL_METADATA_REGISTERED", model.modelArtifactId);
    return HttpResponse.json(model, { status: 201 });
  })),
  http.get("/api/v1/audit", demoResolver((request) => {
    const { user, workspaceId, role } = scopeFor(request);
    return HttpResponse.json(db.audit.filter((entry) => entry.workspaceId === workspaceId && (role === "ADMIN" || entry.actorUserId === user.userId)));
  })),
  http.post("/api/v1/experiments", demoResolver(async (request) => {
    const { user, workspaceId } = scopeFor(request);
    const input = validateConfig(await body(request));
    validateSelection(input, user, workspaceId);
    const experiment: Experiment = { ...input, experimentId: newId("exp"), workspaceId, ownerUserId: user.userId, status: "DRAFT", cancelRequested: false, task: input.task ?? "Countdown", maxGenerations: input.maxGenerations, datasetIds: input.datasetIds, modelVersion: "pending", candidatesPerGeneration: input.candidatesPerGeneration ?? 8, baseSeed: 91400, configHash: "pending-submit", createdAt: now() };
    db.experiments.unshift(experiment);
    audit(user, workspaceId, "EXPERIMENT_CREATED", experiment.experimentId);
    return HttpResponse.json(experiment, { status: 201 });
  })),
  http.patch("/api/v1/experiments/:experimentId", demoResolver(async (request, params) => {
    const { user, workspaceId } = scopeFor(request);
    const experiment = canReadExperiment(request, String(params.experimentId)) ?? fail(404, "Experiment not found.");
    if (experiment.ownerUserId !== user.userId) return fail(403, "Only the owner can edit this draft.");
    if (experiment.status !== "DRAFT") return fail(409, "Only draft configurations can be edited.");
    const input = validateConfig(await body(request));
    validateSelection(input, user, workspaceId);
    Object.assign(experiment, input);
    audit(user, workspaceId, "EXPERIMENT_UPDATED", experiment.experimentId);
    return HttpResponse.json(experiment);
  })),
  http.delete("/api/v1/experiments/:experimentId", demoResolver((request, params) => {
    const { user, workspaceId } = scopeFor(request);
    const experiment = canReadExperiment(request, String(params.experimentId)) ?? fail(404, "Experiment not found.");
    if (experiment.ownerUserId !== user.userId) return fail(403, "Only the owner can archive this experiment.");
    if (isBusy(experiment) || experiment.status === "PAUSED") return fail(409, "Cancel the run before archiving its experiment.");
    experiment.archivedAt = now();
    audit(user, workspaceId, "EXPERIMENT_ARCHIVED", experiment.experimentId);
    return new HttpResponse(null, { status: 204 });
  })),
  http.post("/api/v1/experiments/:experimentId/submit", demoResolver((request, params) => {
    const { user, workspaceId } = scopeFor(request);
    const experiment = canReadExperiment(request, String(params.experimentId)) ?? fail(404, "Experiment not found.");
    if (experiment.ownerUserId !== user.userId) return fail(403, "Only the owner can submit this experiment.");
    if (experiment.status !== "DRAFT") return fail(409, "This experiment has already been submitted.");
    validateSelection(experiment, user, workspaceId);
    const busy = busyWorkers();
    for (const id of experiment.workerIds ?? []) {
      const worker = db.workers.find((item) => item.workerId === id);
      if (!worker || worker.status !== "ONLINE" || !["ADMITTED", "ADMITTED_LIMITED"].includes(worker.admissionStatus) || busy.has(id)) return fail(409, "A selected worker is busy, offline or not admitted. Choose another active grant.");
    }
    experiment.status = "QUEUED";
    experiment.completedGenerations = 0; experiment.mockCandidateProgress = 0;
    experiment.currentGenerationId = `${experiment.experimentId}-g1`;
    experiment.configHash = `demo-config:${newId("snapshot")}`;
    audit(user, workspaceId, "RUN_SUBMISSION_REQUESTED", experiment.experimentId);
    setTimeout(() => {
      void withDemoStore(() => {
        const current = db.experiments.find((item) => item.experimentId === experiment.experimentId);
        if (current?.status === "QUEUED" && !current.cancelRequested) {
          current.status = "RUNNING";
          current.startedAt = now();
          current.mockTickAt = Date.now();
          persist();
        }
      });
    }, 4500);
    return HttpResponse.json(experiment, { status: 202 });
  })),
  http.post("/api/v1/experiments/:experimentId/cancel", demoResolver((request, params) => {
    const { user, workspaceId, role } = scopeFor(request);
    const experiment = canReadExperiment(request, String(params.experimentId)) ?? fail(404, "Experiment not found.");
    if (role !== "ADMIN" && experiment.ownerUserId !== user.userId) return fail(403, "You cannot cancel this experiment.");
    if ((!isBusy(experiment) && experiment.status !== "PAUSED") || experiment.cancelRequested) return fail(409, "This run is not cancellable or cancellation is already pending.");
    if (experiment.status === "PAUSED") { experiment.status = "CANCELLED"; experiment.completedAt = now(); persist(); }
    else cancelSimulation(experiment);
    audit(user, workspaceId, "RUN_CANCEL_REQUESTED", experiment.experimentId);
    return HttpResponse.json(experiment, { status: 202 });
  })),
  http.post("/api/v1/demo/experiments/:experimentId/complete", demoResolver((request, params) => {
    const { user, workspaceId, role } = scopeFor(request);
    const experiment = canReadExperiment(request, String(params.experimentId)) ?? fail(404, "Experiment not found.");
    if (role !== "ADMIN" && experiment.ownerUserId !== user.userId) return fail(403, "You cannot control this run.");
    if (experiment.status !== "RUNNING" || experiment.cancelRequested) return fail(409, "Only a running, non-cancelling demo run can complete.");
    experiment.status = "COMPLETED";
    experiment.completedAt = now();
    finalizeReleases();
    audit(user, workspaceId, "DEMO_RUNTIME_COMPLETED", experiment.experimentId);
    return HttpResponse.json(experiment);
  })),
];

export function visibleWorkers(request: Request) {
  const { workspaceId } = scopeFor(request);
  const ids = db.pools.filter((pool) => pool.workspaceId === workspaceId).flatMap((pool) => pool.workerIds);
  return db.workers.filter((worker) => ids.includes(worker.workerId)).map(workerTelemetry);
}
