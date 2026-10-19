import type { Generation } from '../types/generation';
import { apiGet } from './client';

export function getGenerations(experimentId: string): Promise<Generation[]> {
  return apiGet<Generation[]>(`/api/v1/experiments/${experimentId}/generations`);
}

export function getGeneration(experimentId: string, generationId: string): Promise<Generation> {
  return apiGet<Generation>(`/api/v1/experiments/${experimentId}/generations/${generationId}`);
}
