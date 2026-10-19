import { activeLanguage,useProduct } from "@heteroes/product-ui";
import { useRef } from "react";
import { Link } from "react-router";
import { browserNotificationsEnabled,useBrowserOptIn,useNotifications } from "../../hooks/useNotifications";
import { useNow } from "../../hooks/useNow";
import { fillTemplate } from "../../lib/eventText";
import { describeNotification,relativeTime,type NotificationItem } from "../../lib/notificationText";

/** The bell in the top bar: unread count, the latest notifications, and an opt-in for browser notifications. */
export function NotificationBell() {
  const { t } = useProduct();
  const menu = useRef<HTMLDetailsElement>(null);
  const optIn = useBrowserOptIn();
  const now = useNow();
  const sentence = (item: NotificationItem) => { const d = describeNotification(item); return fillTemplate(t(d.title), d.params); };
  const { items, unread, loading, failed, read } = useNotifications(item => {
    if (!browserNotificationsEnabled()) return;
    try { new Notification("HeteroES", { body: sentence(item), tag: item.id }); } catch { /* the page notice is enough */ }
  });
  const close = () => { if (menu.current) menu.current.open = false; };

  return (
    <details className="bell" ref={menu}>
      <summary className="btn" aria-label={unread ? `${t("Notifications")}: ${unread} ${t("unread")}` : t("Notifications")}>
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 9a6 6 0 0 1 12 0c0 6 2.5 7.5 2.5 7.5h-17S6 15 6 9" /><path d="M10 20a2 2 0 0 0 4 0" /></svg>
        {unread > 0 && <span className="bell-badge" role="status">{unread > 99 ? "99+" : unread}</span>}
      </summary>
      <div className="bell-panel">
        <div className="bell-head"><b>{t("Notifications")}</b><button type="button" className="link" disabled={!unread || read.isPending} onClick={() => read.mutate({ all: true })}>{t("Mark all as read")}</button></div>
        {loading ? <p className="hint bell-empty">{t("Loading…")}</p> : failed ? <p className="hint bell-empty">{t("Could not load notifications.")}</p> : items.length === 0 ? <p className="hint bell-empty">{t("Nothing yet. You will be told when an experiment ends or something needs you.")}</p> : (
          <ul>
            {items.map(item => {
              const d = describeNotification(item);
              return (
                <li key={item.id} className={`bell-item bell-${d.tone}${item.read ? " read" : ""}`}>
                  <Link to={item.target ?? "/dashboard"} onClick={() => { if (!item.read) read.mutate({ ids: [item.id] }); close(); }}>
                    <span>{sentence(item)}</span><small>{relativeTime(item.created, now, activeLanguage())}</small>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
        {optIn.supported && <label className="bell-optin"><input type="checkbox" checked={optIn.on} onChange={() => void optIn.toggle()} /> {t("Also show browser notifications")}</label>}
      </div>
    </details>
  );
}
