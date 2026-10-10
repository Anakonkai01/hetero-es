const TIME_ZONE = "Asia/Ho_Chi_Minh";

export const NOT_AVAILABLE = "Not available yet";

function partsOf(date: Date, options: Intl.DateTimeFormatOptions) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: TIME_ZONE,
    hourCycle: "h23",
    ...options,
  }).formatToParts(date);

  return Object.fromEntries(parts.map((part) => [part.type, part.value]));
}

/** Formats an ISO timestamp as "Oct 03 09:12" in GMT+7. */
export function formatDateTime(iso?: string): string {
  if (!iso) {
    return "—";
  }

  const p = partsOf(new Date(iso), {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });

  return `${p.month} ${p.day} ${p.hour}:${p.minute}`;
}

/** Formats a timestamp as "HH:MM:SS" in GMT+7. */
export function formatClock(value?: string | number | Date): string {
  if (value === undefined) {
    return "—";
  }

  const p = partsOf(new Date(value), {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  return `${p.hour}:${p.minute}:${p.second}`;
}

export function formatOptionalDateTime(
  iso: string | undefined,
  fallback: string,
): string {
  return iso ? formatDateTime(iso) : fallback;
}

/** Shortens long identifiers, e.g. "exp-8d21c4f0aa11" -> "exp-8d21…aa11". */
export function shortId(id: string): string {
  return id.length > 14 ? `${id.slice(0, 8)}…${id.slice(-4)}` : id;
}

export function formatReward(value?: number): string {
  return value === undefined ? NOT_AVAILABLE : value.toFixed(2);
}

export function formatGb(megabytes: number, digits = 0): string {
  return `${(megabytes / 1024).toFixed(digits)} GB`;
}

export function shortGpuName(name: string): string {
  return name.replace(/^NVIDIA GeForce /, "");
}

export function formatBytes(bytes?: number): string {
  if (bytes === undefined) {
    return "—";
  }

  if (bytes >= 1024 * 1024) {
    return `${Math.round(bytes / (1024 * 1024))} MB`;
  }

  return `${(bytes / 1024).toFixed(1)} KB`;
}

export function percent(done: number, total: number): number {
  return total > 0 ? (100 * done) / total : 0;
}

/** Formats an ISO timestamp as "Oct 03 15:38:12" in GMT+7. */
export function formatFullDateTime(iso: string): string {
  const p = partsOf(new Date(iso), {
    month: "short",
    day: "2-digit",
  });

  return `${p.month} ${p.day} ${formatClock(iso)}`;
}
