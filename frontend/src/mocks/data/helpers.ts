const NOW = Date.now();

/** Deterministic pseudo-random hex string, so mock IDs stay stable between reloads. */
export function hx(seed: string, length: number): string {
  let hash = 2166136261;

  for (let i = 0; i < seed.length; i++) {
    hash ^= seed.charCodeAt(i);
    hash = Math.imul(hash, 16777619) >>> 0;
  }

  let out = "";
  let x = hash;

  while (out.length < length) {
    x = (Math.imul(x, 1103515245) + 12345) >>> 0;
    out += (x >>> 8).toString(16).padStart(6, "0");
  }

  return out.slice(0, length);
}

/** ISO timestamp for a moment `minutes` (+ `seconds`) before the mock server started. */
export function minutesAgo(minutes: number, seconds = 0): string {
  return new Date(NOW - minutes * 60_000 - seconds * 1000).toISOString();
}

export function minutesFromNow(minutes: number): string {
  return new Date(NOW + minutes * 60_000).toISOString();
}

export function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
