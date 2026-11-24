export interface CoordinatorOption {
  deviceId: string;
  gpu?: boolean;
  updateSecondsPerSeed?: number | null;
}

/**
 * The coordinator the run form pre-selects when the creator has not chosen one. Owner rule (2026-11-24): a GPU
 * coordinator whenever one is available, because a CPU update is several times slower.
 *
 * - The lab's default is kept when it is a GPU coordinator.
 * - Otherwise a GPU coordinator is suggested. A strict run keeps one weight set per GPU (D1), so its coordinator's GPU
 *   cannot also work: the slowest GPU (largest measured update time) coordinates and the faster ones work. Other
 *   decoders may share the coordinator's GPU with a worker, so the fastest GPU coordinates.
 * - Without any GPU coordinator, the lab's default (if still offered) or nothing.
 */
export function suggestCoordinator(
  devices: CoordinatorOption[],
  labDefault: string | null | undefined,
  strict: boolean,
): string {
  const gpus = devices.filter((d) => d.gpu);
  if (labDefault && gpus.some((d) => d.deviceId === labDefault)) return labDefault;
  if (gpus.length) {
    const speed = (d: CoordinatorOption) => d.updateSecondsPerSeed ?? (strict ? -1 : Number.POSITIVE_INFINITY);
    const ranked = [...gpus].sort((a, b) => (strict ? speed(b) - speed(a) : speed(a) - speed(b)));
    return ranked[0].deviceId;
  }
  return labDefault && devices.some((d) => d.deviceId === labDefault) ? labDefault : '';
}
