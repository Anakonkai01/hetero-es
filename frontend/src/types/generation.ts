export type GenerationStatus = "RUNNING" | "COMPLETED";

export interface Generation {
  experimentId: string;
  generationId: string;

  modelVersion: string;

  status: GenerationStatus;

  candidateCount: number;
  committedCandidateCount: number;

  rewardMean?: number;
  rewardBest?: number;

  startedAt?: string;
  completedAt?: string;
}
