import type { SystemEvent } from '../types/event';
import { apiGet } from './client';

export function getEvents(): Promise<SystemEvent[]> {
  return apiGet<SystemEvent[]>('/api/v1/events');
}
