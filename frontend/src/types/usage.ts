export interface UsageSummary {
  generatedTokens?: number;
  auditGeneratedTokens?: number;
  gpuSeconds?: number;
  workerGpuSeconds?: number;
  coordinatorUpdateGpuSeconds?: number;
  partial: boolean;
  unavailable?: boolean;
}

export interface CandidateUsage {
  formatVersion: 1;
  generatedTokens: number[];
  device: 'cpu' | 'cuda';
  wallSeconds: number;
}
