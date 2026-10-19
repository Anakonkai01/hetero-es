import type { Worker } from '../types/worker';
import { apiGet } from './client';

export function getWorkers(): Promise<Worker[]> {
  return apiGet<Worker[]>('/api/v1/workers');
}

export function getWorker(workerId: string): Promise<Worker> {
  return apiGet<Worker>(`/api/v1/workers/${workerId}`);
}
