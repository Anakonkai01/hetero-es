export type WorkspaceRole = "ADMIN" | "PARTICIPANT";

export interface User {
  userId: string;
  username: string;
  displayName: string;
  canCreateWorkspace: boolean;
  email?: string;
  bio?: string;
}

export interface Workspace {
  workspaceId: string;
  name: string;
  role: WorkspaceRole;
  description?: string;
  creatorUserId?: string;
}

export interface Session {
  user: User;
  workspaces: Workspace[];
}

export interface LoginResponse extends Session {
  /** A demo credential only. A real backend must implement its own session contract. */
  demoToken?: string;
  accessToken?: string;
}

export interface WorkspaceMember {
  user: User;
  role: WorkspaceRole;
}

export interface WorkerPool {
  poolId: string;
  workspaceId: string;
  name: string;
  workerIds: string[];
  drainingWorkerIds: string[];
}

export type GrantStatus = "ACTIVE" | "RELEASING" | "RELEASED";

export interface WorkerGrant {
  grantId: string;
  workspaceId: string;
  poolId: string;
  userId: string;
  workerIds: string[];
  status: GrantStatus;
  requestedBy?: "ADMIN" | "PARTICIPANT";
  createdAt: string;
}

export interface WorkerRequest {
  requestId: string;
  workspaceId: string;
  poolId: string;
  userId: string;
  workerIds: string[];
  reason: string;
  status: "PENDING" | "APPROVED" | "REJECTED";
  createdAt: string;
}

export interface ModelRegistration {
  modelArtifactId: string;
  workspaceId: string;
  ownerUserId: string;
  name: string;
  source: "REFERENCE" | "UPLOAD_METADATA";
  reference?: string;
  revision?: string;
  files?: { name: string; sizeBytes: number }[];
  /** Metadata only: no weights are transferred or validated in this prototype. */
  status: "REGISTERED";
  createdAt: string;
}

export interface ResourceOverview {
  submissions: ResourceSubmission[];
  invitations: WorkspaceInvitation[];
  pools: WorkerPool[];
  grants: WorkerGrant[];
  requests: WorkerRequest[];
  members: WorkspaceMember[];
  busyWorkerIds: string[];
  reservedWorkerIds: string[];
}

export interface AuditEntry {
  auditId: string;
  workspaceId: string;
  actorUserId: string;
  action: string;
  targetId: string;
  createdAt: string;
}

export interface ResourceSubmission {
  submissionId: string; workspaceId: string; workerId: string; ownerUserId: string;
  gpuName: string; ownerName: string; status: "PENDING" | "APPROVED" | "REJECTED"; createdAt: string;
}
export interface WorkspaceInvitation {
  invitationId: string; workspaceId: string; workspaceName: string; email: string;
  status: "PENDING" | "ACCEPTED"; createdAt: string;
}
