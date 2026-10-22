import type { ResourceHistoryPoint, ResourceObservation } from '@heteroes/product-ui';
export type AdmissionStatus =
  'PENDING_VERIFICATION' | 'INELIGIBLE' | 'ELIGIBLE_BUT_NOT_BENEFICIAL' | 'ADMITTED_LIMITED' | 'ADMITTED' | 'APPROVED';

export type WorkerStatus = 'ONLINE' | 'OFFLINE';

export interface WorkerProfile {
  gpuIndex?: number;
  gpuName: string;
  vramTotalMb: number;
  vramFreeMb?: number;

  throughputTokensPerSecond?: number;
  safeChunkSize?: number;
}

export interface Worker {
  stopReason?: string | null;
  blockedRunId?: string | null;
  telemetry?: ResourceObservation | null;
  telemetryHistory?: ResourceHistoryPoint[];
  displayName?: string;
  physicalResourceId?: string;
  approvalStatus?: string;
  workerId: string;
  ownerUserId?: string;
  temperatureC?: number;
  utilizationPercent?: number;
  activeExperimentName?: string;
  allocatedTo?: string;
  contributionEnabled?: boolean;

  status: WorkerStatus;
  admissionStatus: AdmissionStatus;
  admissionReason?: string;

  profile: WorkerProfile;

  lastHeartbeatAt?: string;
}
