import type { AuditEntry, ResourceSubmission, WorkspaceInvitation, ModelRegistration, User, WorkerGrant, WorkerPool, WorkerRequest, Workspace, WorkspaceMember } from "../types/access";
import type { SystemEvent } from "../types/event";
import type { Dataset } from "../types/dataset";
import type { Experiment } from "../types/experiment";
import type { Worker } from "../types/worker";
import { mockExperiments } from "./data/experiments";
import { mockWorkers } from "./data/workers";

const STORAGE_KEY = "heteroes.local-demo.v1";
export const demoUsers: User[] = [
  { userId: "user-admin", username: "admin", email: "admin@example.test", displayName: "Lab Admin", canCreateWorkspace: true },
  { userId: "user-an", username: "an", email: "an@example.test", displayName: "An", canCreateWorkspace: true },
  { userId: "user-binh", username: "binh", email: "binh@example.test", displayName: "Bình", canCreateWorkspace: true },
];

interface DemoStore {
  submissions: ResourceSubmission[];
  invitations: WorkspaceInvitation[];
  runtimeEvents: SystemEvent[];
  profiles: User[];
  datasets: Dataset[];
  version: 1;
  workspaces: { workspaceId: string; name: string; description?: string; creatorUserId?: string }[];
  memberships: { userId: string; workspaceId: string; role: Workspace["role"] }[];
  sessions: { token: string; userId: string; expiresAt: number }[];
  pools: WorkerPool[];
  workers: Worker[];
  requests: WorkerRequest[];
  grants: WorkerGrant[];
  models: ModelRegistration[];
  experiments: Experiment[];
  audit: AuditEntry[];
}

function seed(): DemoStore {
  const workspaceId = "ws-lab";
  const workerIds = mockWorkers.slice(0, 2).map((worker) => worker.workerId);
  return {
    version: 1,
    submissions: [], invitations: [],
    profiles: structuredClone(demoUsers), datasets: [], runtimeEvents: [],
    workspaces: [{ workspaceId, name: "GPU Lab", description: "Shared GPU workspace", creatorUserId: "user-admin" }, { workspaceId: "ws-private", name: "Private Lab", creatorUserId: "user-admin" }],
    memberships: [
      { userId: "user-admin", workspaceId, role: "ADMIN" },
      { userId: "user-admin", workspaceId: "ws-private", role: "ADMIN" },
      { userId: "user-an", workspaceId, role: "PARTICIPANT" },
      { userId: "user-binh", workspaceId, role: "PARTICIPANT" },
    ],
    sessions: [],
    pools: [{ poolId: "pool-lab", workspaceId, name: "Lab GPU Pool", workerIds: [...mockWorkers.map((worker) => worker.workerId), "wk-demo-free"], drainingWorkerIds: [] }],
    workers: [...structuredClone(mockWorkers).map((worker, i) => ({ ...worker, ownerUserId: i < 2 ? "user-an" : "user-admin" })), { workerId: "wk-demo-free", ownerUserId: "user-binh", status: "ONLINE", admissionStatus: "ADMITTED", profile: { gpuName: "Demo GPU · 12 GiB", vramTotalMb: 12288 }, lastHeartbeatAt: new Date().toISOString() }],
    requests: [],
    grants: [{ grantId: "grant-sample", workspaceId, poolId: "pool-lab", userId: "user-an", workerIds, status: "ACTIVE", createdAt: new Date().toISOString() }],
    models: [{ modelArtifactId: "model-sample", workspaceId, ownerUserId: "user-an", name: "Qwen2.5-0.5B-Instruct (sample)", source: "REFERENCE", reference: "Qwen/Qwen2.5-0.5B-Instruct", revision: "demo-version", status: "REGISTERED", createdAt: new Date().toISOString() }],
    // Preserve the existing monitoring fixtures. They precede the new allocation flow.
    experiments: structuredClone(mockExperiments).map((experiment) => ({ ...experiment, workspaceId, ownerUserId: "user-an", workerIds, modelArtifactId: "model-sample" })),
    audit: [],
  };
}

function restore(): DemoStore {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
    if (value && typeof value === "object" && "version" in value && value.version === 1) {
      const candidate = value as DemoStore;
      if ([candidate.workspaces, candidate.memberships, candidate.sessions, candidate.pools, candidate.workers, candidate.requests, candidate.grants, candidate.models, candidate.experiments, candidate.audit].every(Array.isArray)) return { ...candidate, submissions: candidate.submissions ?? [], invitations: candidate.invitations ?? [], runtimeEvents: candidate.runtimeEvents ?? [], profiles: candidate.profiles ?? structuredClone(demoUsers), datasets: candidate.datasets ?? [], workers: candidate.workers.map((w, i) => ({ ownerUserId: i < 2 ? "user-an" : "user-admin", ...w })) };
    }
  } catch { /* A damaged demo snapshot is replaced with sample data. */ }
  return seed();
}

export const demoStore = restore();
let useMemoryOnly = false;
export function refreshStore() {
  if (useMemoryOnly) return;
  try {
    if (localStorage.getItem(STORAGE_KEY)) Object.assign(demoStore, restore());
  } catch { useMemoryOnly = true; }
}
let storeQueue: Promise<unknown> = Promise.resolve();
export function withDemoStore<T>(operation: () => T | Promise<T>): Promise<T> {
  const run = async () => { refreshStore(); return operation(); };
  const result = storeQueue.then(() => typeof navigator !== "undefined" && navigator.locks
    ? navigator.locks.request("heteroes-local-demo-store", run)
    : run());
  storeQueue = result.catch(() => {});
  return result;
}
export const newId = (prefix: string) => `${prefix}-${crypto.randomUUID()}`;
export const now = () => new Date().toISOString();
export function persist() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(demoStore)); }
  catch { useMemoryOnly = true; }
}

export function audit(user: User, workspaceId: string, action: string, targetId: string) {
  demoStore.audit.unshift({ auditId: newId("audit"), workspaceId, actorUserId: user.userId, action, targetId, createdAt: now() });
  persist();
}

export function workspacesFor(user: User): Workspace[] {
  return demoStore.memberships.filter((membership) => membership.userId === user.userId).flatMap((membership) => {
    const workspace = demoStore.workspaces.find((item) => item.workspaceId === membership.workspaceId);
    return workspace ? [{ ...workspace, role: membership.role }] : [];
  });
}

export function membersFor(workspaceId: string): WorkspaceMember[] {
  return demoStore.memberships.filter((membership) => membership.workspaceId === workspaceId).flatMap((membership) => {
    const user = demoStore.profiles.find((item) => item.userId === membership.userId);
    return user ? [{ user, role: membership.role }] : [];
  });
}

export function currentUser(request: Request) {
  const token = request.headers.get("Authorization")?.replace(/^Bearer /, "");
  const session = demoStore.sessions.find((item) => item.token === token && item.expiresAt > Date.now());
  return demoStore.profiles.find((user) => user.userId === session?.userId);
}

export function isBusy(experiment: Experiment) {
  return !experiment.archivedAt && (experiment.status === "RUNNING" || experiment.status === "PAUSING" || experiment.status === "QUEUED");
}

export function busyWorkers() {
  return new Set(demoStore.experiments.filter(isBusy).flatMap((experiment) => experiment.workerIds ?? []));
}

export function ownedWorkerIds(userId: string, workspaceId: string) {
  return demoStore.grants.filter((grant) => grant.userId === userId && grant.workspaceId === workspaceId && grant.status === "ACTIVE").flatMap((grant) => grant.workerIds);
}

/** Finalize only after all simulated runtime work using the resource has stopped. */
export function finalizeReleases() {
  const busy = busyWorkers();
  for (const grant of demoStore.grants) {
    if (grant.status === "RELEASING" && !grant.workerIds.some((id) => busy.has(id))) grant.status = "RELEASED";
  }
  for (const pool of demoStore.pools) {
    const removed = pool.drainingWorkerIds.filter((id) => !busy.has(id));
    if (removed.length) {
      pool.workerIds = pool.workerIds.filter((id) => !removed.includes(id));
      pool.drainingWorkerIds = pool.drainingWorkerIds.filter((id) => !removed.includes(id));
      // Grants reserve a group; releasing a removed member releases the whole group.
      for (const grant of demoStore.grants.filter((item) => item.poolId === pool.poolId && item.status !== "RELEASED" && item.workerIds.some((id) => removed.includes(id)))) {
        grant.status = grant.workerIds.some((id) => busy.has(id)) ? "RELEASING" : "RELEASED";
      }
    }
  }
  persist();
}

export function cancelSimulation(experiment: Experiment) {
  if (!isBusy(experiment)) return;
  experiment.cancelRequested = true;
  persist();
  setTimeout(() => {
    void withDemoStore(() => {
      const current = demoStore.experiments.find((item) => item.experimentId === experiment.experimentId);
      if (current && isBusy(current) && current.cancelRequested) {
        current.status = "CANCELLED";
        current.completedAt = now();
        finalizeReleases();
      }
    });
  }, 5000);
}

// Resume confirmations after a reload; these timers remain entirely within the mock.
for (const experiment of demoStore.experiments) {
  if (isBusy(experiment) && experiment.cancelRequested) cancelSimulation(experiment);
  else if (experiment.status === "QUEUED") {
    setTimeout(() => {
      void withDemoStore(() => {
        const current = demoStore.experiments.find((item) => item.experimentId === experiment.experimentId);
        if (current?.status === "QUEUED" && !current.cancelRequested) {
          current.status = "RUNNING";
          current.startedAt = now();
          current.mockTickAt = Date.now();
          persist();
        }
      });
    }, 4500);
  }
}
