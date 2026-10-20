import type { UsageSummary } from './usage';

export type GenerationStatus = 'RUNNING' | 'COMPLETED' | 'CANCELLED' | 'FAILED';

export interface Generation {
  usage?: UsageSummary;
  experimentId: string;
  generationId: string;

  modelVersion: string;

  status: GenerationStatus;

  candidateCount: number;
  committedCandidateCount: number;

  validationReward?: number;
  rewardMean?: number;
  rewardBest?: number;

  startedAt?: string;
  completedAt?: string;
}
