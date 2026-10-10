export type AdmissionStatus =
  | "INELIGIBLE"
  | "ELIGIBLE_BUT_NOT_BENEFICIAL"
  | "ADMITTED_LIMITED"
  | "ADMITTED";

export type WorkerStatus = "ONLINE" | "OFFLINE";

export interface WorkerProfile {
  gpuName: string;
  vramTotalMb: number;
  vramFreeMb?: number;

  throughputTokensPerSecond?: number;
  safeChunkSize?: number;
}

export interface Worker {
  workerId: string;
  ownerUserId?: string;
  temperatureC?: number;
  utilizationPercent?: number;
  activeExperimentName?: string;
  allocatedTo?: string;

  status: WorkerStatus;
  admissionStatus: AdmissionStatus;
  admissionReason?: string;

  profile: WorkerProfile;

  lastHeartbeatAt?: string;
}
