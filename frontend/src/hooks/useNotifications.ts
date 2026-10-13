import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../api/client";
import { useSession } from "../app/session";
import { IS_MOCK } from "../lib/dataSource";
import { newUnread, type NotificationItem } from "../lib/notificationText";

type Listing = { items: NotificationItem[]; unread: number };
const OPT_IN = "heteroes.browser-notifications";

export const browserNotificationsSupported = () => typeof Notification !== "undefined";
export function browserNotificationsEnabled(): boolean {
  try { return browserNotificationsSupported() && Notification.permission === "granted" && localStorage.getItem(OPT_IN) === "1"; } catch { return false; }
}
export async function setBrowserNotifications(on: boolean): Promise<boolean> {
  if (!browserNotificationsSupported()) return false;
  if (on && Notification.permission !== "granted") await Notification.requestPermission();
  const enabled = on && Notification.permission === "granted";
  try { localStorage.setItem(OPT_IN, enabled ? "1" : "0"); } catch { /* the choice then lasts for this visit only */ }
  return enabled;
}

/** The bell's data: polled every few seconds, with a browser notification for each new unread one when the person has opted in. */
export function useNotifications(announce: (item: NotificationItem) => void) {
  const { session } = useSession();
  const cache = useQueryClient();
  const enabled = !IS_MOCK && Boolean(session);
  const query = useQuery({ queryKey: ["notifications", session?.user.userId], queryFn: () => apiGet<Listing>("/api/v1/notifications?limit=30"), enabled, refetchInterval: 10000, retry: 1 });
  const seen = useRef<Set<string> | undefined>(undefined);
  const announceRef = useRef(announce);
  useEffect(() => { announceRef.current = announce; });
  useEffect(() => {
    if (!query.data) return;
    for (const item of newUnread(seen.current, query.data.items)) announceRef.current(item);
    seen.current = new Set(query.data.items.map(item => item.id));
  }, [query.data]);
  const read = useMutation({
    mutationFn: (body: { ids: string[] } | { all: true }) => apiPost("/api/v1/notifications/read", body),
    onSuccess: () => cache.invalidateQueries({ queryKey: ["notifications"] }),
  });
  return { items: query.data?.items ?? [], unread: query.data?.unread ?? 0, loading: query.isPending && enabled, failed: query.isError, read };
}

export function useBrowserOptIn() {
  const [on, setOn] = useState(browserNotificationsEnabled);
  return { supported: browserNotificationsSupported(), on, toggle: async () => setOn(await setBrowserNotifications(!on)) };
}
