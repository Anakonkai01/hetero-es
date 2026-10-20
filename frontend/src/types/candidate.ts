import type { CandidateUsage } from './usage';

export type CandidateStatus = 'PENDING' | 'LEASED' | 'RUNNING' | 'COMMITTED';

export interface Candidate {
  usage?: CandidateUsage;
  experimentId: string;
  generationId: string;
  candidateId: string;

  attemptId?: string;

  modelVersion: string;

  seed: number | string;
  noiseRecipeHash: string;

  batchIds: string[];

  generationConfigHash: string;

  leaseToken?: string;
  leaseDeadline?: string;

  workerId?: string;

  status: CandidateStatus;

  reward?: number;
}
