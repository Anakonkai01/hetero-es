import type { ResourceHistoryPoint, ResourceObservation } from '@heteroes/product-ui';
type SetupState = {
  installed: boolean;
  running: boolean;
  profileAvailable?: boolean;
  progress: {
    stage: string;
    file?: string;
    received?: number;
    total?: number;
    iteration?: number;
    code?: string;
  };
};
export type State = {
  compute: {
    pending?: boolean;
    network: string;
    coordinator: boolean;
    host: string;
    eligible: boolean;
    addresses: { host: string; name: string; network: string }[];
  };
  telemetry?: ResourceObservation | null;
  telemetryHistory?: ResourceHistoryPoint[];
  serverUrl: string;
  defaultLabUrl?: string;
  build?: string;
  signedIn: boolean;
  session?: {
    user: {
      displayName: string;
    };
  };
  connection: string;
  device?: {
    deviceId: string;
    workerId: string;
    displayName: string;
    approvalStatus: string;
  };
  selfTest?: {
    passed: boolean;
    gpuName: string;
    vramTotalMb: number;
    gpuUUID?: string;
  };
  setup: SetupState;
  agent?: {
    enabled: boolean;
    drained: boolean;
    error?: string;
    startError?: string;
    assignments: {
      assignmentId: string;
      epoch?: number;
      ready?: boolean;
      workerAlive: boolean | null;
      coordinatorAlive: boolean | null;
    }[];
  };
};
type ConnectionCheck = { step: string; status: string; code: string };
export type ConnectionReport = {
  checks: ConnectionCheck[];
  assignments: { assignmentId: string; replayOnly?: boolean; checks: ConnectionCheck[] }[];
};
declare global {
  interface Window {
    worker: {
      call: (
        action: string,
        args?: Record<string, unknown>,
      ) => Promise<{
        ok: boolean;
        result?: unknown;
        error?: string;
      }>;
    };
  }
}
