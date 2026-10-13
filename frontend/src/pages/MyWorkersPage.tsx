import {useProduct} from '@heteroes/product-ui';
import { useState } from "react";
import { connectMyWorker, submitResource } from "../api/access";
import { useSession } from "../app/session";
import { useAccessMutation, useMyWorkers, useMyResourceSubmissions } from "../hooks/useAccess";
import { PageHeader } from "../components/ui/PageHeader";
import { QueryState } from "../components/common/QueryState";
import { Modal } from "../components/ui/Modal";
import { ChipIcon, PlusIcon } from "../components/ui/Icons";
import { WorkerRegistration } from "../components/workspace/WorkerRegistration";
import { WorkerMetrics } from "../components/workspace/WorkerMetrics";
import type { Worker } from "../types/worker";

export function MyWorkersPage() { return IS_MOCK ? <MockMyWorkersPage /> : <RuntimeWorkersPage />; }

function MockMyWorkersPage() {
  const {t}=useProduct();
  const { session, workspace } = useSession(); const query = useMyWorkers(); const requests = useMyResourceSubmissions();
  const connection = useAccessMutation(connectMyWorker); const submit = useAccessMutation(submitResource);
  const [registering, setRegistering] = useState(false); const [selection, setSelection] = useState<Worker | null>(null);
  const [workspaceId, setWorkspaceId] = useState(workspace?.workspaceId ?? "");
  const [disconnecting, setDisconnecting] = useState<{ workerId: string; workspaceId: string } | null>(null);
  const chosen = session?.workspaces.find((w) => w.workspaceId === workspaceId);
  return <><PageHeader title={t("Workers")} description={t("Registered GPUs and workspace connections.")} actions={<button className="btn accent" onClick={() => setRegistering(true)}><PlusIcon />{t("Register Worker")}</button>} />
    <div className="workspace-summary-strip"><span><b>{query.data?.length ?? 0}</b> {t("registered")}</span><span><b>{query.data?.filter((w) => w.workspaceId).length ?? 0}</b> {t("connected")}</span><span><b>{requests.data?.filter((r) => r.status === "PENDING").length ?? 0}</b> {t("pending admissions")}</span></div>
    <QueryState isPending={query.isPending || requests.isPending} isError={query.isError || requests.isError} hasData={Boolean(query.data && requests.data)} title={t("Worker registry unavailable")}>
      <div className="owned-worker-grid">{query.data?.map((w) => {
        const pending = requests.data?.find((r) => r.workerId === w.workerId && r.status === "PENDING");
        return <section className="card owned-worker-card" key={w.workerId}><div className="ch"><span className="resource-glyph"><ChipIcon /></span><span className={`resource-state ${w.workspaceId ? "allocated" : pending ? "draining" : "free"}`}>{w.workspaceId ? "Connected" : pending ? "Pending approval" : "Registered"}</span></div><div className="cb"><h2>{w.profile.gpuName}</h2><p className="mono mut resource-id">{w.workerId}</p><WorkerMetrics worker={w} /><dl className="resource-facts"><div><dt>{t("Workspace")}</dt><dd>{session?.workspaces.find((s) => s.workspaceId === w.workspaceId)?.name ?? (w.workspaceId ? "Connected workspace" : pending ? session?.workspaces.find((s) => s.workspaceId === pending.workspaceId)?.name ?? "Pending workspace" : "—")}</dd></div><div><dt>{t("Experiment")}</dt><dd>{w.activeExperimentName ?? "Idle"}</dd></div></dl>
          <div className="resource-detail-actions">{w.workspaceId ? <button className="btn" disabled={!session?.workspaces.some((s) => s.workspaceId === w.workspaceId)} onClick={() => { connection.reset(); setDisconnecting({ workerId: w.workerId, workspaceId: w.workspaceId! }); }}>{t("Disconnect")}</button> : <button className="btn accent" disabled={Boolean(pending) || !session?.workspaces.length} onClick={() => { submit.reset(); setWorkspaceId(workspace?.workspaceId ?? session?.workspaces[0]?.workspaceId ?? ""); setSelection(w); }}>{pending ? "Approval pending" : "Add to workspace"}</button>}</div>
        </div></section>;
      })}</div>
      {!query.data?.length && <div className="empty"><ChipIcon /><b>{t("No registered Workers")}</b></div>}
    </QueryState>
    {registering && <WorkerRegistration onClose={() => setRegistering(false)} onRegistered={() => setRegistering(false)} />}
    {selection && <Modal title={t("Workspace admission")} subtitle={selection.profile.gpuName} onClose={() => setSelection(null)}><form className="modal-form" onSubmit={(e) => { e.preventDefault(); void submit.mutateAsync({ workspaceId, workerId: selection.workerId }).then(() => setSelection(null)).catch(() => {}); }}>
      <label className="fg">{t("Workspace")}<select className="sel" required value={workspaceId} onChange={(e) => setWorkspaceId(e.target.value)}>{session?.workspaces.map((s) => <option key={s.workspaceId} value={s.workspaceId}>{s.name}</option>)}</select></label>
      <div className={`registration-banner ${chosen?.role === "ADMIN" ? "admin" : ""}`}><span className={`role-pill ${chosen?.role.toLowerCase()}`}>{t("Role:")}{" "}{chosen?.role === "ADMIN" ? t("Admin") : t("Participant")}</span><span>{chosen?.role === "ADMIN" ? t("Direct admission") : t("Admin approval required")}</span></div>
      {submit.error && <p className="note err" role="alert">{submit.error.message}</p>}<div className="modal-footer"><button className="btn" type="button" onClick={() => setSelection(null)}>{t("Cancel")}</button><button className={`btn ${chosen?.role === "ADMIN" ? "violet" : "accent"}`} disabled={submit.isPending || !chosen}>{chosen?.role === "ADMIN" ? t("Add to Resources") : t("Submit for approval")}</button></div>
    </form></Modal>}
    {disconnecting && <Modal title={t("Disconnect Worker")} onClose={() => setDisconnecting(null)}><div className="modal-form"><p>{t("Workspace connection will be removed. Active allocations and tasks must be stopped first.")}</p>{connection.error && <p className="note err" role="alert">{connection.error.message}</p>}<div className="modal-footer"><button className="btn" onClick={() => setDisconnecting(null)}>{t("Cancel")}</button><button className="btn dng" disabled={connection.isPending} onClick={() => void connection.mutateAsync({ ...disconnecting, action: "DISCONNECT" }).then(() => setDisconnecting(null)).catch(() => {})}>{t("Disconnect")}</button></div></div></Modal>}
  </>;
}
import { IS_MOCK } from "../lib/dataSource";
import { RuntimeWorkersPage } from "./RuntimePages";
