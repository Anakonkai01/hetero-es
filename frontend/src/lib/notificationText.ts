export type NotificationItem = {
  id: string;
  kind: string;
  params?: Record<string, string | number>;
  target?: string;
  created?: string;
  read?: boolean;
};
export type NotificationText = {
  title: string;
  params: Record<string, string | number>;
  tone: 'ok' | 'warn' | 'err' | 'info';
};

// English templates are the translation keys (see eventText.ts for the placeholder rule).
export const TEMPLATES: Record<string, [string, NotificationText['tone']]> = {
  'account.request': ['New account request: {displayName} (@{username})', 'warn'],
  'device.request': ['A GPU computer is waiting for approval: {name}', 'warn'],
  'account.approved': ['Your account was approved', 'ok'],
  'account.rejected': ['Your account request was declined', 'err'],
  'account.suspended': ['Your account was suspended', 'err'],
  'run.completed': ['Experiment finished: {name}', 'ok'],
  'run.failed': ['Experiment failed: {name}', 'err'],
  'run.cancelled': ['Experiment cancelled: {name}', 'warn'],
};

export function describeNotification(item: Pick<NotificationItem, 'kind' | 'params'>): NotificationText {
  const known = TEMPLATES[item.kind];
  if (known) return { title: known[0], params: item.params ?? {}, tone: known[1] };
  const phrase = item.kind.replace(/[._]/g, ' ').trim();
  return { title: phrase ? phrase[0].toUpperCase() + phrase.slice(1) : 'Notification', params: {}, tone: 'info' };
}

/** Unread notifications that were not in the previous list. The first list ever seen announces nothing. */
export function newUnread<T extends { id: string; read?: boolean }>(
  previous: Set<string> | undefined,
  items: T[],
): T[] {
  if (!previous) return [];
  return items.filter((item) => !item.read && !previous.has(item.id));
}

export function relativeTime(iso: string | undefined, nowMs: number, language: 'vi' | 'en'): string {
  const then = iso ? Date.parse(iso) : NaN;
  if (!Number.isFinite(then)) return '';
  const seconds = Math.max(0, (nowMs - then) / 1000);
  const vi = language === 'vi';
  if (seconds < 45) return vi ? 'vừa xong' : 'just now';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return vi ? `${minutes} phút trước` : `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return vi ? `${hours} giờ trước` : `${hours} h ago`;
  const days = Math.round(hours / 24);
  return vi ? `${days} ngày trước` : `${days} d ago`;
}
