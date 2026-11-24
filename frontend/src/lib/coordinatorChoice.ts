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
 * - Otherwise prefer the GPU with the fastest measured update. Strict sharing is checked by the lab against the
 *   selected model and qualification when a run is submitted.
 * - Without a GPU, strict runs have no suggestion. Earlier layouts may use the offered lab default.
 */
export function suggestCoordinator(
  devices: CoordinatorOption[],
  labDefault: string | null | undefined,
  strict: boolean,
): string {
  const gpus = devices.filter((d) => d.gpu);
  if (labDefault && gpus.some((d) => d.deviceId === labDefault)) return labDefault;
  if (gpus.length) {
    const speed = (d: CoordinatorOption) => d.updateSecondsPerSeed ?? Number.POSITIVE_INFINITY;
    const ranked = gpus.sort((a, b) => speed(a) - speed(b));
    return ranked[0].deviceId;
  }
  return !strict && labDefault && devices.some((d) => d.deviceId === labDefault) ? labDefault : '';
}
