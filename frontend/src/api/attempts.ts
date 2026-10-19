import type { Attempt } from '../types/attempt';
import { apiGet } from './client';

export function getAttempt(attemptId: string): Promise<Attempt> {
  return apiGet<Attempt>(`/api/v1/attempts/${attemptId}`);
}
