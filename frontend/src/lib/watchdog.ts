/** D11 watchdog settings of a Recipe v3 run, checked like the lab does (`heteroes.v3.options.validate_watchdog`). */
export const MAX_WATCHDOG_SECONDS = 7 * 86400;

export interface WatchdogSettings {
  hardCapSeconds?: number;
  stallSeconds?: number;
}

/** An empty field keeps the lab default. Returns the settings to send, or the sentence that explains the problem. */
export function watchdogSettings(hardCap: string, stall: string): WatchdogSettings | { error: string } {
  const settings: WatchdogSettings = {};
  for (const [key, text, low] of [
    ['hardCapSeconds', hardCap, 60],
    ['stallSeconds', stall, 30],
  ] as const) {
    if (text.trim() === '') continue;
    const value = Number(text);
    if (!Number.isFinite(value) || value < low || value > MAX_WATCHDOG_SECONDS)
      return {
        error:
          key === 'hardCapSeconds'
            ? 'The generation hard cap is 60 to 604800 seconds.'
            : 'The stall time is 30 to 604800 seconds.',
      };
    settings[key] = value;
  }
  if (settings.hardCapSeconds !== undefined && settings.stallSeconds !== undefined)
    if (settings.stallSeconds >= settings.hardCapSeconds)
      return { error: 'The stall time must be shorter than the generation hard cap.' };
  return settings;
}
