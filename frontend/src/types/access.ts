export type WorkspaceRole = "ADMIN" | "PARTICIPANT";

export interface User {
  userId: string;
  username: string;
  displayName: string;
  canCreateWorkspace: boolean;
  accountStatus?: "PENDING" | "ACTIVE" | "REJECTED" | "SUSPENDED";
  platformAdmin?: boolean;
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
  accessToken: string;
}

export interface WorkspaceMember {
  user: User;
  role: WorkspaceRole;
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


export interface WorkspaceInvitation {
  invitationId: string; workspaceId: string; workspaceName: string; email: string;
  status: "PENDING" | "ACCEPTED"; createdAt: string;
}
