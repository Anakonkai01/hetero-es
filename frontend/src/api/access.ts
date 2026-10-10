import type { ResourceSubmission, WorkspaceInvitation } from "../types/access";
import type { Dataset, DatasetUpload } from "../types/dataset";
import type { User } from "../types/access";
import { apiDelete, apiGet, apiPatch, apiPost } from "./client";
import type { AuditEntry, LoginResponse, ModelRegistration, ResourceOverview, Session, WorkerGrant, WorkerPool, WorkerRequest, Workspace } from "../types/access";
import type { Worker } from "../types/worker";

export const getSession = () => apiGet<Session>("/api/v1/auth/session");
export const login = (input: { username: string; password: string }) => apiPost<LoginResponse>("/api/v1/auth/login", input);
export const logout = () => apiPost<void>("/api/v1/auth/logout");
export const getWorkspaces = () => apiGet<Workspace[]>("/api/v1/workspaces");
export const createWorkspace = (name: string) => apiPost<Workspace>("/api/v1/workspaces", { name });
export const getResourceOverview = () => apiGet<ResourceOverview>("/api/v1/resources");
export const createPool = (name: string) => apiPost<WorkerPool>("/api/v1/pools", { name });
export const getWorkerRegistry = () => apiGet<Worker[]>("/api/v1/worker-registry");
export const addPoolWorker = (input: { poolId: string; workerId: string }) => apiPost<WorkerPool>(`/api/v1/pools/${input.poolId}/workers`, { workerId: input.workerId });
export const registerDemoWorker = (input: { poolId: string; workerId: string; gpuName: string; vramTotalMb: number }) => apiPost<Worker>("/api/v1/demo/workers", input);
export const removePoolWorker = (input: { poolId: string; workerId: string }) => apiDelete<WorkerPool>(`/api/v1/pools/${input.poolId}/workers/${input.workerId}`);
export const requestWorkers = (input: { poolId?: string; workerIds: string[]; reason: string }) => apiPost<WorkerRequest>("/api/v1/worker-requests", input);
export const decideWorkerRequest = (input: { requestId: string; decision: "APPROVE" | "REJECT" }) => apiPost<WorkerRequest>(`/api/v1/worker-requests/${input.requestId}/decision`, { decision: input.decision });
export const releaseGrant = (input: { grantId: string; action: "return" | "revoke" }) => apiPost<WorkerGrant>(`/api/v1/grants/${input.grantId}/${input.action}`);
export const getModels = () => apiGet<ModelRegistration[]>("/api/v1/models");
export const registerModel = (input: Omit<ModelRegistration, "modelArtifactId" | "workspaceId" | "ownerUserId" | "status" | "createdAt">) => apiPost<ModelRegistration>("/api/v1/models", input);
export const getAudit = () => apiGet<AuditEntry[]>("/api/v1/audit");

export const updateProfile = (input: { displayName: string; email: string; bio: string }) => apiPatch<User>("/api/v1/profile", input);
export const deleteWorkspace = (id: string) => apiDelete(`/api/v1/workspaces/${id}`);
export const getMyWorkers = () => apiGet<(Worker & { workspaceId?: string })[]>("/api/v1/my-workers");
export const createMyWorker = (input: { gpuName: string; vramTotalMb: number }) => apiPost<Worker>("/api/v1/my-workers", input);
export const connectMyWorker = (input: { workerId: string; action: "CONNECT" | "DISCONNECT"; workspaceId?: string }) => apiPost<Worker>(`/api/v1/my-workers/${input.workerId}/connection`, { action: input.action, workspaceId: input.workspaceId });
export const getDatasets = () => apiGet<Dataset[]>("/api/v1/datasets");
export const uploadDataset = (input: DatasetUpload) => apiPost<Dataset>("/api/v1/datasets", input);

export const submitResource = (input: { workspaceId: string; workerId: string }) => apiPost<ResourceSubmission>(`/api/v1/workspaces/${input.workspaceId}/resources`, { workerId: input.workerId });
export const decideResourceSubmission = (input: { submissionId: string; decision: "APPROVE" | "REJECT" }) => apiPost<ResourceSubmission>(`/api/v1/resource-submissions/${input.submissionId}/decision`, input);
export const getMyResourceSubmissions = () => apiGet<ResourceSubmission[]>("/api/v1/my-resource-submissions");
export const inviteMember = (input: { workspaceId: string; email: string }) => apiPost<WorkspaceInvitation>(`/api/v1/workspaces/${input.workspaceId}/invitations`, { email: input.email });
export const getMyInvitations = () => apiGet<WorkspaceInvitation[]>("/api/v1/my-invitations");
export const acceptInvitation = (id: string) => apiPost<WorkspaceInvitation>(`/api/v1/my-invitations/${id}/accept`);
