import { useProduct } from '@heteroes/product-ui';
import { Link } from "react-router";
import { useSession } from "../app/session";
import { QueryState } from "../components/common/QueryState";
import { WorkerFleet } from '../components/workers/WorkerFleet';
import { useAudit,useResources } from "../hooks/useAccess";
import { useWorkers } from "../hooks/useWorkers";
import { LabMembership } from './LabMembership';
export function WorkspacePage() {
  const {t}=useProduct();
  const { workspace } = useSession(); const resources = useResources(); const workers = useWorkers(); const audit = useAudit();
  return <><div className={`workspace-hero ${workspace?.role === "ADMIN" ? "admin" : "participant"}`}><div className="workspace-hero-heading"><div><h1>{workspace?.name}</h1><p>{t("Shared GPU pool · persistent queue")}</p></div><span className="role-pill">{workspace?.role}</span></div><div className="workspace-hero-footer"><Link className="btn accent" to="/experiments/new">{t("Create experiment")}</Link><Link className="btn" to="/experiments">{t("Experiments")}</Link></div></div>
    <QueryState isPending={resources.isPending || workers.isPending} isError={resources.isError || workers.isError} hasData={Boolean(resources.data && workers.data)} title={t("Workspace resources unavailable")}>
      <WorkerFleet />
      <LabMembership />
      <section className="card"><div className="ch"><h2>{t("Activity")}</h2></div><div className="cb">{audit.isError && <p role="alert">{t("Activity unavailable")}</p>}{audit.data?.slice(0, 20).map((entry) => <p key={entry.auditId} className="activity-entry"><time>{new Date(entry.createdAt).toLocaleTimeString()}</time><span>{t(entry.action)}<span className="hint"> · {entry.actorUserId}</span></span></p>)}</div></section>
    </QueryState></>;
}
