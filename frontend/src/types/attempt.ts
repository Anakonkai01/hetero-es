export type AttemptStatus = 'RUNNING' | 'SUCCEEDED' | 'FAILED';

export interface Attempt {
  experimentId: string;
  generationId: string;
  candidateId: string;
  attemptId: string;

  workerId: string;
  modelVersion: string;

  leaseToken?: string;

  status: AttemptStatus;

  startedAt?: string;
  completedAt?: string;

  errorType?: string;
}
