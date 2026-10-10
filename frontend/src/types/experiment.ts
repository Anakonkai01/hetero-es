export type ExperimentStatus =
  | "PAUSING"
  | "PAUSED"
  | "DRAFT"
  | "QUEUED"
  | "RUNNING"
  | "COMPLETED"
  | "CANCELLED";

export type SchedulerPolicy = "capacity-weighted" | "round-robin";

export type SyncMode = "synchronous" | "asynchronous";

export interface Experiment {
  experimentId: string;
  name: string;
  workspaceId?: string;
  ownerUserId?: string;
  workerIds?: string[];
  modelArtifactId?: string;
  archivedAt?: string;
  maxGenerations?: number;
  datasetIds?: string[];
  completedGenerations?: number;
  mockCandidateProgress?: number;
  mockTickAt?: number;
  validationScore?: number;
  testScore?: number;
  checkpointSavedAt?: string;

  status: ExperimentStatus;
  cancelRequested: boolean;

  modelName: string;
  modelVersion: string;
  task: string;

  schedulerPolicy: SchedulerPolicy;
  syncMode: SyncMode;

  candidatesPerGeneration: number;
  baseSeed: number;
  configHash: string;

  currentGenerationId?: string;

  createdAt: string;
  startedAt?: string;
  completedAt?: string;
}

export interface CreateExperimentRequest {
  name: string;
  modelName: string;
  schedulerPolicy: SchedulerPolicy;
  syncMode: SyncMode;
  workerIds?: string[];
  modelArtifactId?: string;
  task?: string;
  maxGenerations?: number;
  candidatesPerGeneration?: number;
  datasetIds?: string[];
}
