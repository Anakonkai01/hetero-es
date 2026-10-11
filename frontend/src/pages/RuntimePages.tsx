import {useProduct} from '@heteroes/product-ui';
import { Link } from "react-router";
import { useSession } from "../app/session";
import { useAudit, useModels, useResources } from "../hooks/useAccess";
import { useWorkers } from "../hooks/useWorkers";
import { PageHeader } from "../components/ui/PageHeader";
import { QueryState } from "../components/common/QueryState";
import { WorkerMetrics } from "../components/workspace/WorkerMetrics";
import { LabMembership } from './LabMembership';
import { LabProfile } from './LabProfile';
import { LabDevices } from './LabDevices';
import { LabContributions } from './LabContributions';
import {useQuery} from '@tanstack/react-query';
import {apiGet} from '../api/client';

export function RuntimeWorkspacePage() {
  const {t}=useProduct();
  const { workspace } = useSession(); const resources = useResources(); const workers = useWorkers(); const audit = useAudit();
  return <><div className={`workspace-hero ${workspace?.role === "ADMIN" ? "admin" : "participant"}`}><div className="workspace-hero-heading"><div><h1>{workspace?.name}</h1><p>{t("Shared GPU pool · persistent queue")}</p></div><span className="role-pill">{workspace?.role}</span></div><div className="workspace-hero-footer"><Link className="btn accent" to="/experiments/new">{t("Create experiment")}</Link><Link className="btn" to="/experiments">{t("Experiments")}</Link></div></div>
    <QueryState isPending={resources.isPending || workers.isPending} isError={resources.isError || workers.isError} hasData={Boolean(resources.data && workers.data)} title={t("Workspace resources unavailable")}>
      <RuntimeWorkerCards />
      <LabMembership />
      <section className="card"><div className="ch"><h2>{t("Activity")}</h2></div><div className="cb">{audit.isError && <p role="alert">{t("Activity unavailable")}</p>}{audit.data?.slice(0, 20).map((entry) => <p key={entry.auditId}>{entry.action} · {entry.actorUserId} · {new Date(entry.createdAt).toLocaleString()}</p>)}</div></section>
    </QueryState></>;
}

function RuntimeWorkerCards() {
  const {t}=useProduct();
  const workers = useWorkers();
  return <QueryState isPending={workers.isPending} isError={workers.isError} hasData={Boolean(workers.data)} title={t("Worker registry unavailable")}><div className="resource-grid">{workers.data?.map((worker) => <section className="card" key={worker.workerId}><div className="ch"><h2>{worker.profile.gpuName}</h2><span className={`connection-tag ${worker.status.toLowerCase()}`}>{worker.status}</span></div><div className="cb demo-form"><Link className="link mono" to={`/workers/${worker.workerId}`}>{worker.workerId}</Link>{worker.status === "ONLINE" ? <WorkerMetrics worker={worker} /> : <p>{t("GPU metrics unavailable")}</p>}<p>{worker.admissionReason}</p><p>{t("Allocation:")}{worker.allocatedTo ?? "Available"}</p></div></section>)}</div></QueryState>;
}

export function RuntimeWorkersPage() {
  const {t}=useProduct();
  const {workspace}=useSession();
  const health=useQuery({queryKey:['control-health'],queryFn:()=>apiGet<{agentMode?:boolean}>('/api/v1/health')});
  return <><PageHeader title={t("Workers")} description={t("Live probes of configured GPUs in the selected workspace.")} /><LabDevices />{health.data && !health.data.agentMode && <LabContributions />}{workspace ? <RuntimeWorkerCards /> : <p>{t("Join a workspace to view its live GPU inventory.")}</p>}</>;
}

export function RuntimeModelsPage() {
  const {t}=useProduct();
  const models = useModels();
  return <><PageHeader title={t("Models")} description={t("Pinned runtime model")} /><QueryState isPending={models.isPending} isError={models.isError} hasData={Boolean(models.data)} title={t("Model capabilities unavailable")}><section className="card"><div className="cb demo-form">{models.data?.map((model) => <div key={model.modelArtifactId}><h2>{model.name}</h2><p className="mono">{model.revision}</p></div>)}<button className="btn" disabled title={t("Only the pinned Qwen checkpoint is supported")}>{t("Register / upload model")}</button><Link className="btn pri" to="/experiments/new">{t("Create experiment")}</Link></div></section></QueryState></>;
}

export function RuntimeProfilePage() {
  return <LabProfile />;
}
