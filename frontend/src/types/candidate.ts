export type CandidateStatus =
  | "PENDING"
  | "LEASED"
  | "RUNNING"
  | "COMMITTED";

export interface Candidate {
  experimentId: string;
  generationId: string;
  candidateId: string;

  attemptId?: string;

  modelVersion: string;

  seed: number;
  noiseRecipeHash: string;

  batchIds: string[];

  generationConfigHash: string;

  leaseToken?: string;
  leaseDeadline?: string;

  workerId?: string;

  status: CandidateStatus;

  reward?: number;
}
