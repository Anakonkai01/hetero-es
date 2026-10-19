import type { Candidate } from '../types/candidate';
import { apiGet } from './client';

export function getCandidates(generationId: string): Promise<Candidate[]> {
  return apiGet<Candidate[]>(`/api/v1/generations/${generationId}/candidates`);
}

export function getCandidate(candidateId: string): Promise<Candidate> {
  return apiGet<Candidate>(`/api/v1/candidates/${candidateId}`);
}
