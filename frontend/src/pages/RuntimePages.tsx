import {StudyAssets} from '../components/experiments/StudyAssets';
import {useState} from 'react';
import {useProduct,Status,ResourceTelemetry} from '@heteroes/product-ui';
import { Link } from "react-router";
import { useSession } from "../app/session";
import { useAudit, useModels, useResources } from "../hooks/useAccess";
import { useWorkers } from "../hooks/useWorkers";
import { PageHeader } from "../components/ui/PageHeader";
import { QueryState } from "../components/common/QueryState";
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
      <section className="card"><div className="ch"><h2>{t("Activity")}</h2></div><div className="cb">{audit.isError && <p role="alert">{t("Activity unavailable")}</p>}{audit.data?.slice(0, 20).map((entry) => <p key={entry.auditId} className="activity-entry"><time>{new Date(entry.createdAt).toLocaleTimeString()}</time><span>{t(entry.action)}<span className="hint"> · {entry.actorUserId}</span></span></p>)}</div></section>
    </QueryState></>;
}

function RuntimeWorkerCards() {
 const {t}=useProduct();const workers=useWorkers();
 return <QueryState isPending={workers.isPending} isError={workers.isError} hasData={Boolean(workers.data)} title={t('Worker registry unavailable')}><div className="resource-grid">{workers.data?.map(worker=><section className="card" key={worker.workerId}><div className="ch resource-title"><div><h2>{worker.displayName??worker.profile.gpuName}</h2><span className="hint">{worker.profile.gpuName} · {(worker.profile.vramTotalMb/1024).toFixed(1)} GiB</span></div><Status value={worker.status}/></div><div className="cb"><Link className="link mono" to={`/workers/${worker.workerId}`}>{worker.workerId}</Link><div className="device-statuses"><Status value={worker.approvalStatus??worker.admissionStatus}/><Status value={worker.contributionEnabled?'ON':'OFF'}/></div><div className="resource-assignment"><span>{t('Allocation')}: </span>{worker.allocatedTo?<Link to={`/experiments/${worker.allocatedTo}`}>{worker.activeExperimentName??worker.allocatedTo}</Link>:t('No active allocation')}</div><ResourceTelemetry observation={worker.telemetry} history={worker.telemetryHistory} online={worker.status==='ONLINE'} compact/><details className="advanced-panel"><summary>{t('Device identity')}</summary><div><p className="device-identity">{worker.physicalResourceId??t('Physical GPU identity unavailable')}</p><p className="info-caption">{worker.admissionReason??t('Contribution, connectivity and resource ownership are independent states.')}</p></div></details></div></section>)}</div>{workers.data?.length===0&&<div className="empty"><b>{t('No workers registered')}</b><span>{t('Pair a GPU computer to start monitoring it here.')}</span></div>}</QueryState>;
}

export function RuntimeWorkersPage() {
  const {t}=useProduct();
  const {workspace}=useSession();
  const health=useQuery({queryKey:['control-health'],queryFn:()=>apiGet<{agentMode?:boolean}>('/api/v1/health')});
  const [view,setView]=useState('fleet');
  return <><PageHeader title={t('Workers')} description={t('Live GPU resources, allocation and hardware measurements.')} actions={<button className="btn pri" onClick={()=>setView('devices')}>+ {t('Add a GPU computer')}</button>}/>
  {health.data?.agentMode?<><div className="tabs" role="tablist" aria-label={t('GPU views')}><button className={view==='fleet'?'tab on':'tab'} role="tab" aria-selected={view==='fleet'} onClick={()=>setView('fleet')}>{t('Workspace GPU fleet')}</button><button className={view==='devices'?'tab on':'tab'} role="tab" aria-selected={view==='devices'} onClick={()=>setView('devices')}>{t('My devices & contribution')}</button></div>{view==='devices'?<LabDevices/>:workspace?<RuntimeWorkerCards/>:<p>{t('Join a workspace to view its live GPU inventory.')}</p>}</>:<><LabContributions/>{workspace&&<RuntimeWorkerCards/>}</>}
  </>;
}

export function RuntimeModelsPage() {
 const {t}=useProduct();const models=useModels();
 return <><PageHeader title={t('Models')} description={t('Pinned model references used by the current runtime.')}/><QueryState isPending={models.isPending} isError={models.isError} hasData={Boolean(models.data)} title={t('Model capabilities unavailable')}><div className="resource-grid">{models.data?.map(model=><section className="card model-card" key={model.modelArtifactId}><Status value="Pinned"/><h2>{model.name}</h2><p className="hint">{model.reference??model.name}</p><dl className="model-identity"><dt>{t('Pinned revision')}</dt><dd className="mono">{model.revision}</dd></dl><p className="info-caption">{t('Workers use this fixed model revision for reproducible evaluations.')}</p><div className="acts"><Link className="btn pri" to="/experiments/new">{t('Create experiment')} →</Link></div></section>)}</div><StudyAssets/></QueryState></>;
}

export function RuntimeProfilePage() {
  return <LabProfile />;
}
