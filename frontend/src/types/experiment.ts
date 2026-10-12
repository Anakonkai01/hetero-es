export type ExperimentStatus =
  | "STARTING"
  | "CANCELLING"
  | "RECOVERING"
  | "DRAINING"
  | "FAILED"
  | "PAUSING"
  | "PAUSED"
  | "DRAFT"
  | "QUEUED"
  | "RUNNING"
  | "COMPLETED"
  | "CANCELLED";

export type SchedulerPolicy = "capacity-weighted" | "round-robin" | "greedy";

export type SyncMode = "synchronous" | "asynchronous";

export interface Experiment {
  recipeVersion?: number;
  batchSize?:number;
  batchSeed?:number;
  sigmaSchedule?:string;
  sigmaMinimum?:number;
  maxNewTokens?:number;
  validationInterval?:number;
  studyMetrics?:{testLocked:boolean;independentReloadPassed?:boolean};
  monitoringPartial?: boolean;
  experimentId: string;
  name: string;
  workspaceId?: string;
  ownerUserId?: string;
  workerIds?: string[];
  coordinatorDeviceId?: string;
  backupPolicy?: {interval:number;retain:number};
  requestedBackupPolicy?: {interval:number;retain:number};
  waitingReason?: string;
  cloudSync?: {status:string;lastCloudGeneration?:number;errorType?:string};
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
  committedCandidateCount?: number;
  failureReason?: string;
  alpha?: number;
  sigma?: number;
  decodeEngine?: string;

  status: ExperimentStatus;
  cancelRequested: boolean;

  modelName: string;
  modelVersion: string;
  task: string;

  schedulerPolicy: SchedulerPolicy;
  syncMode: SyncMode;

  candidatesPerGeneration: number;
  baseSeed?: number;
  configHash: string;

  currentGenerationId?: string;

  createdAt: string;
  startedAt?: string;
  completedAt?: string;
}

export interface CreateExperimentRequest {
  recipeVersion?: number;
  batchSize?:number;
  batchSeed?:number;
  sigmaSchedule?:string;
  sigmaMinimum?:number;
  maxNewTokens?:number;
  validationInterval?:number;
  name: string;
  modelName: string;
  schedulerPolicy: SchedulerPolicy;
  syncMode: SyncMode;
  workerIds?: string[];
  coordinatorDeviceId?: string;
  backupPolicy?: {interval:number;retain:number};
  requestedBackupPolicy?: {interval:number;retain:number};
  waitingReason?: string;
  cloudSync?: {status:string;lastCloudGeneration?:number;errorType?:string};
  modelArtifactId?: string;
  task?: string;
  maxGenerations?: number;
  candidatesPerGeneration?: number;
  datasetIds?: string[];
  alpha?: number;
  sigma?: number;
  decodeEngine?: string;
}
