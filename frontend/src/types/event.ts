export type EventSeverity = 'INFO' | 'WARNING' | 'ERROR';

export interface SystemEvent {
  eventId: string;
  timestamp: string;

  eventType: string;
  severity: EventSeverity;

  message: string;

  experimentId?: string;
  generationId?: string;
  candidateId?: string;
  attemptId?: string;
  workerId?: string;

  details?: Record<string, unknown>;
}
