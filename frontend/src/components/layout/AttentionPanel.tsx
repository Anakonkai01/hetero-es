import { useProduct } from "@heteroes/product-ui";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { apiGet } from "../../api/client";
import { useSession } from "../../app/session";
import { fillTemplate } from "../../lib/eventText";
import type { User } from "../../types/access";
type Item = {
    key: string;
    tone: "warn" | "err" | "info";
    text: string;
    to: string;
    action: string;
};
/** "Needs you": the few things only a person can resolve, each with a link to where it is done. */
export function AttentionPanel({ dispatchHeld, runtimeIssue }: {
    dispatchHeld?: boolean;
    runtimeIssue?: string | null;
}) {
    const { t } = useProduct();
    const { session } = useSession();
    const administrator = Boolean(session?.user.platformAdmin && session.user.accountStatus === "ACTIVE");
    const users = useQuery({ queryKey: ["platform-users", session?.user.userId], queryFn: () => apiGet<User[]>("/api/v1/platform/users"), enabled: administrator, refetchInterval: 10000 });
    const devices = useQuery({ queryKey: ["attention-devices", session?.user.userId], queryFn: () => apiGet<{
            approvalStatus: string;
        }[]>(administrator ? "/api/v1/platform/devices" : "/api/v1/devices"), enabled: Boolean(session), refetchInterval: 10000, retry: 1 });
    const items: Item[] = [];
    const accounts = users.data?.filter(user => user.accountStatus === "PENDING").length ?? 0;
    const pendingDevices = devices.data?.filter(device => device.approvalStatus === "PENDING").length ?? 0;
    if (session && session.user.accountStatus !== "ACTIVE")
        items.push({ key: "account", tone: "warn", text: fillTemplate(t("Your account is {status}. An administrator has to approve it."), { status: t(session.user.accountStatus ?? "PENDING") }), to: "/get-started", action: t("What to do meanwhile") });
    if (accounts)
        items.push({ key: "accounts", tone: "warn", text: fillTemplate(t(accounts === 1 ? "{n} account is waiting for approval." : "{n} accounts are waiting for approval."), { n: accounts }), to: "/operations", action: t("Review requests") });
    if (pendingDevices)
        items.push({ key: "devices", tone: "warn", text: fillTemplate(t(administrator ? "{n} GPU computer(s) wait for approval." : "{n} of your GPU computer(s) wait for administrator approval."), { n: pendingDevices }), to: administrator ? "/operations" : "/workers", action: t(administrator ? "Review devices" : "My GPU computers") });
    if (dispatchHeld)
        items.push({ key: "held", tone: "info", text: t("The queue is held: new experiments wait until an administrator reopens it."), to: "/operations", action: t("Lab operations") });
    if (runtimeIssue)
        items.push({ key: "runtime", tone: "err", text: runtimeIssue, to: "/operations", action: t("Lab operations") });
    return (<section className="card attention" aria-label={t("Needs your attention")}>
      <div className="ch"><h2>{t("Needs your attention")}</h2>{items.length > 0 && <span className="count-badge">{items.length}</span>}</div>
      <div className="cb">
        {items.length === 0 ? <p className="attention-ok"><span aria-hidden="true">✓</span> {t("Nothing is waiting for you.")}</p> : (<ul className="attention-list">
            {items.map(item => <li key={item.key} className={`attention-${item.tone}`}><span>{item.text}</span><Link className="btn" to={item.to}>{item.action}</Link></li>)}
          </ul>)}
      </div>
    </section>);
}
