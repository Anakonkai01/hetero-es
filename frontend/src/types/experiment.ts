import type { UsageSummary } from './usage';

export type WeightSpace =
  | { kind: 'full' }
  | { kind: 'subset'; include: string[] }
  | { kind: 'lora'; rank: number; alpha: number; targetModules: string[] };
export type DeclarativeScorer = {
  kind: 'declarative';
  name: string;
  version: number;
  codeSha256: null;
  config: Record<string, unknown>;
};
// Researcher code run by the coordinator device only (the lab adds codeSha256 and pins it in the plan)
export type PythonScorer = {
  kind: 'python';
  name: string;
  version: number;
  codeSha256: string | null;
  config: Record<string, never>;
};
export type PythonCode = {
  role: 'scorer' | 'coefficients';
  name: string;
  function: string;
  source: string;
  codeSha256?: string;
};
export interface V3Settings {
  weightSpace: WeightSpace;
  antithetic: boolean;
  coefficientRule: string;
  scorer: DeclarativeScorer | PythonScorer;
  pythonCode: PythonCode[];
  systemPrompt: string | null;
  promptFormat: 'chat' | 'raw' | null;
  alphaSchedule: string;
  alphaMinimum: number | null;
  momentumBeta: number | null;
  momentumWindow: number;
  evalChunk: number | null;
  sampler: string;
  candidateSeedNamespace: string | null;
}

export type ExperimentStatus =
  | 'STARTING'
  | 'CANCELLING'
  | 'RECOVERING'
  | 'DRAINING'
  | 'FAILED'
  | 'PAUSING'
  | 'PAUSED'
  | 'DRAFT'
  | 'QUEUED'
  | 'RUNNING'
  | 'COMPLETED'
  | 'CANCELLED';

export type SchedulerPolicy = 'greedy-tail' | 'greedy';

export type SyncMode = 'synchronous';

export interface Experiment extends Partial<V3Settings> {
  noiseEngineVersion?: string;
  workerIdentities?: Record<string, { name: string; gpuName?: string; gpuIndex?: number }>;
  workerBlocks?: Record<string, { reason: string; blockedAt?: number }>;
  usageSummary?: UsageSummary;
  allowJoin?: boolean;
  membershipRequests?: { changeId: string; workerId: string; action: 'JOIN' | 'LEAVE' | 'RETRY'; actor: string }[];
  membership?: {
    generation?: number;
    members?: string[];
    left?: string[];
    refused?: { changeId: string; reason: string }[];
  };
  auditSummary?: {
    completed: number;
    selected?: number;
    mismatches: number;
    quarantinedWorkers: { worker_id: string; reason: string }[];
  };
  recipeVersion?: number;
  batchSize?: number;
  batchSeed?: number;
  sigmaSchedule?: string;
  sigmaMinimum?: number;
  maxNewTokens?: number;
  validationInterval?: number;
  studyMetrics?: {
    testLocked: boolean;
    independentReloadPassed?: boolean;
    validation?: { generation: number; meanReward: number }[];
  };
  monitoringPartial?: boolean;
  experimentId: string;
  name: string;
  workspaceId?: string;
  ownerUserId?: string;
  workerIds?: string[];
  coordinatorDeviceId?: string;
  backupPolicy?: { interval: number; retain: number };
  requestedBackupPolicy?: { interval: number; retain: number };
  waitingReason?: string;
  cloudSync?: { status: string; lastCloudGeneration?: number; errorType?: string };
  modelArtifactId?: string;
  archivedAt?: string;
  maxGenerations?: number;
  datasetIds?: string[];
  completedGenerations?: number;
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

export interface CreateExperimentRequest extends Partial<V3Settings> {
  recipeVersion?: number;
  batchSize?: number;
  batchSeed?: number;
  sigmaSchedule?: string;
  sigmaMinimum?: number;
  maxNewTokens?: number;
  validationInterval?: number;
  name: string;
  modelName: string;
  schedulerPolicy: SchedulerPolicy;
  syncMode: SyncMode;
  allowJoin?: boolean;
  workerIds?: string[];
  coordinatorDeviceId?: string;
  backupPolicy?: { interval: number; retain: number };
  requestedBackupPolicy?: { interval: number; retain: number };
  waitingReason?: string;
  cloudSync?: { status: string; lastCloudGeneration?: number; errorType?: string };
  modelArtifactId?: string;
  task?: string;
  maxGenerations?: number;
  candidatesPerGeneration?: number;
  datasetIds?: string[];
  alpha?: number;
  sigma?: number;
  decodeEngine?: string;
}
