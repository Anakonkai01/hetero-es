export interface WorkerIdentity {
  name?: string | null;
  displayName?: string | null;
  gpuName?: string | null;
  gpuIndex?: number | null;
  profile?: { gpuName?: string; gpuIndex?: number | null };
  selfTest?: { gpuName?: string; gpuIndex?: number | null };
}

/** Shared human label; IDs remain available in titles and the identity detail. */
export function workerLabel(identity: WorkerIdentity | undefined, workerId: string): string {
  const name = identity?.displayName || identity?.name || workerId;
  const gpu = identity?.gpuName || identity?.profile?.gpuName || identity?.selfTest?.gpuName;
  const index = identity?.gpuIndex ?? identity?.profile?.gpuIndex ?? identity?.selfTest?.gpuIndex;
  return [name, gpu, index == null ? null : `GPU ${index + 1}`].filter(Boolean).join(' · ');
}
