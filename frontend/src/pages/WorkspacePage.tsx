import { useState } from "react";
import { Link, useNavigate } from "react-router";
import * as api from "../api/access";
import { useSession } from "../app/session";
import { useAppState } from "../app/appState";
import { QueryState } from "../components/common/QueryState";
import { Badge } from "../components/ui/Badge";
import { Modal } from "../components/ui/Modal";
import { ChipIcon, PlusIcon } from "../components/ui/Icons";
import { WorkerMetrics } from "../components/workspace/WorkerMetrics";
import { useAccessMutation, useAudit, useMyWorkers, useMyResourceSubmissions, useResources } from "../hooks/useAccess";
import { useWorkers } from "../hooks/useWorkers";

type Panel = "resources" | "members" | "activity";
type Dialog = "invite" | "apply" | "request" | null;

export function WorkspacePage() {
  const { session, workspace, refreshSession } = useSession(); const { flash } = useAppState(); const navigate = useNavigate();
  const resources = useResources(); const workers = useWorkers(); const owned = useMyWorkers(); const submissions = useMyResourceSubmissions(); const audit = useAudit();
  const submit = useAccessMutation(api.submitResource); const invite = useAccessMutation(api.inviteMember);
  const admit = useAccessMutation(api.decideResourceSubmission); const request = useAccessMutation(api.requestWorkers);
  const decide = useAccessMutation(api.decideWorkerRequest); const release = useAccessMutation(api.releaseGrant);
  const remove = useAccessMutation(api.removePoolWorker); const deleteWorkspace = useAccessMutation(api.deleteWorkspace);
  const [panel, setPanel] = useState<Panel>("resources"); const [dialog, setDialog] = useState<Dialog>(null);
  const [selectedId, setSelectedId] = useState(""); const [ownedId, setOwnedId] = useState("");
  const [email, setEmail] = useState(""); const [invited, setInvited] = useState(false);
  const [selectedWorkers, setSelectedWorkers] = useState<string[]>([]); const [reason, setReason] = useState("");
  const [error, setError] = useState(""); const [working, setWorking] = useState(false);
  const [confirmation, setConfirmation] = useState<{ title: string; detail: string; action: () => Promise<unknown> } | null>(null);
  const data = resources.data; const admin = workspace?.role === "ADMIN"; const inventory = workers.data ?? [];
  const selected = inventory.find((w) => w.workerId === selectedId) ?? inventory[0];
  const available = inventory.filter((w) => w.status === "ONLINE" && ["ADMITTED", "ADMITTED_LIMITED"].includes(w.admissionStatus) && !data?.reservedWorkerIds.includes(w.workerId) && !data?.busyWorkerIds.includes(w.workerId) && !data?.pools.some((p) => p.drainingWorkerIds.includes(w.workerId)));
  const pendingSubmissions = data?.submissions.filter((s) => s.status === "PENDING") ?? [];
  const pendingRequests = data?.requests.filter((r) => r.status === "PENDING") ?? [];
  const ownAvailable = owned.data?.filter((w) => !w.workspaceId && !submissions.data?.some((s) => s.workerId === w.workerId && s.status === "PENDING")) ?? [];
  const ownSelected = ownAvailable.find((w) => w.workerId === ownedId) ?? ownAvailable[0];
  const canApply = Boolean(ownSelected) && !working && !owned.isPending && !submissions.isPending && !owned.isError && !submissions.isError;
  const selectedGrant = data?.grants.find((g) => g.status !== "RELEASED" && g.workerIds.includes(selected?.workerId ?? ""));
  const displayUser = (id?: string) => data?.members.find((m) => m.user.userId === id)?.user.displayName ?? id?.replace(/^user-/, "") ?? "—";
  function open(next: Dialog) { setError(""); setInvited(false); setDialog(next); }
  async function run(action: () => Promise<unknown>, message: string, done?: () => void) {
    if (working) return; setWorking(true); setError("");
    try { await action(); flash(message); done?.(); }
    catch (e) { setError(e instanceof Error ? e.message : "Request failed."); }
    finally { setWorking(false); }
  }
  if (!workspace) return <div className="empty"><b>Workspace unavailable</b><Link className="btn" to="/workspace">Workspaces</Link></div>;
  return <>
    <div className={`workspace-hero ${admin ? "admin" : "participant"}`}>
      <div className="workspace-hero-heading"><div><Link className="hero-back" to="/workspace">← Workspaces</Link><h1>{workspace.name}</h1><p>{workspace.description || "Compute workspace"}</p></div><span className={`role-pill ${admin ? "admin" : "participant"}`}>Role: {admin ? "Admin" : "Participant"}</span></div>
      <div className="workspace-hero-footer"><span>Created by <b>{displayUser(workspace.creatorUserId)}</b></span><span><b>{data?.members.length ?? 0}</b> members</span><span><b>{inventory.length}</b> Workers</span><span><b>{data?.busyWorkerIds.length ?? 0}</b> active</span></div>
    </div>
    {!dialog && !confirmation && error && <div className="note err" role="alert">{error}</div>}
    <nav className="workspace-sections" aria-label="Workspace sections">{(["resources", "members", "activity"] as Panel[]).map((p) => <button className={panel === p ? "on" : ""} aria-pressed={panel === p} onClick={() => setPanel(p)} key={p}>{p[0].toUpperCase() + p.slice(1)}{p === "resources" && <span>{inventory.length}</span>}{p === "members" && <span>{data?.members.length ?? 0}</span>}</button>)}</nav>
    <QueryState isPending={resources.isPending || workers.isPending} isError={resources.isError || workers.isError} hasData={Boolean(data && workers.data)} title="Resources unavailable">
      {panel === "resources" && <>
        <div className={`role-toolbar ${admin ? "admin" : "participant"}`}><div><span className="section-eyebrow">{admin ? "ADMINISTRATION" : "RESOURCE ACCESS"}</span><h2>Resources</h2></div><div className="acts">
          <button className="btn" disabled={!available.length} onClick={() => open("request")}>Request Workers</button>
          <button className={`btn ${admin ? "violet" : "accent"}`} onClick={() => open("apply")}><PlusIcon />Apply Worker</button>
        </div></div>
        <div className="resource-split">
          <section className="card resource-inventory"><div className="ch"><h2>Workers</h2><small>{inventory.length} resources</small></div>
            {!inventory.length && <div className="empty"><ChipIcon /><b>No Workers</b></div>}
            {inventory.map((w) => { const allocated = data?.reservedWorkerIds.includes(w.workerId); const busy = data?.busyWorkerIds.includes(w.workerId); const draining = data?.pools.some((p) => p.drainingWorkerIds.includes(w.workerId)); return <button className={`resource-row ${selected?.workerId === w.workerId ? "selected" : ""}`} key={w.workerId} onClick={() => setSelectedId(w.workerId)} aria-pressed={selected?.workerId === w.workerId}>
              <span className="resource-glyph"><ChipIcon /></span><span className="resource-row-text"><b>{w.profile.gpuName}</b><small>{(w.profile.vramTotalMb / 1024).toFixed(0)} GiB · {displayUser(w.ownerUserId)}</small></span><span className={`resource-state ${draining ? "draining" : busy ? "busy" : allocated ? "allocated" : "free"}`}>{draining ? "Draining" : busy ? "Running" : allocated ? "Allocated" : "Available"}</span>
            </button>; })}
          </section>
          <section className="card resource-detail">{selected ? <>
            <div className="ch"><div><span className="section-eyebrow">WORKER DETAILS</span><h2>{selected.profile.gpuName}</h2></div><span className={`connection-tag ${selected.status === "ONLINE" ? "online" : "offline"}`}>{selected.status === "ONLINE" ? "Connected" : "Offline"}</span></div>
            <div className="cb"><p className="mono mut resource-id">{selected.workerId}</p><WorkerMetrics worker={selected} />
              <dl className="resource-facts"><div><dt>Owner</dt><dd>{displayUser(selected.ownerUserId)}</dd></div><div><dt>Allocation</dt><dd>{selectedGrant ? `${displayUser(selectedGrant.userId)} · ${selectedGrant.status}` : "Unallocated"}</dd></div><div><dt>Experiment</dt><dd>{selected.activeExperimentName ?? "Idle"}</dd></div><div><dt>Coordinator</dt><dd>{selected.status === "ONLINE" ? "Connected" : "Disconnected"}</dd></div></dl>
              <div className="resource-detail-actions">
                {selectedGrant?.status === "ACTIVE" && (admin || selectedGrant.userId === session?.user.userId) && <button className="btn" disabled={working} onClick={() => setConfirmation({ title: admin ? "Reclaim Workers" : "Return Workers", detail: `${displayUser(selectedGrant.userId)} · ${selectedGrant.workerIds.length} Worker(s). Active tasks will receive a cancellation request.`, action: () => release.mutateAsync({ grantId: selectedGrant.grantId, action: admin ? "revoke" : "return" }) })}>{admin ? "Reclaim allocation" : "Return allocation"}</button>}
                {admin && <button className="btn dng" disabled={working || data?.pools.some((p) => p.drainingWorkerIds.includes(selected.workerId))} onClick={() => setConfirmation({ title: "Remove Worker", detail: `${selected.profile.gpuName} will be removed from Resources. The related allocation group will be released; active work must stop before removal completes.`, action: () => remove.mutateAsync({ poolId: data!.pools.find((p) => p.workerIds.includes(selected.workerId))!.poolId, workerId: selected.workerId }) })}>Remove from Resources</button>}
              </div>
            </div></> : <div className="empty"><b>Worker details</b><span>No resource selected</span></div>}
          </section>
        </div>
        {(pendingSubmissions.length > 0 || pendingRequests.length > 0) && <div className="request-panels">
          <section className="card"><div className="ch"><h2>Worker admissions</h2><span className="count-badge">{pendingSubmissions.length}</span></div><div className="cb">{!pendingSubmissions.length && <p className="hint">No pending admissions</p>}{pendingSubmissions.map((s) => <div className="request-card" key={s.submissionId}><div><b>{s.gpuName}</b><small>{s.ownerName} · Admission pending</small></div>{admin ? <div className="acts"><button className="btn accent" disabled={working} onClick={() => void run(() => admit.mutateAsync({ submissionId: s.submissionId, decision: "APPROVE" }), "Worker admitted.")}>Accept</button><button className="btn" disabled={working} onClick={() => void run(() => admit.mutateAsync({ submissionId: s.submissionId, decision: "REJECT" }), "Admission rejected.")}>Reject</button></div> : <Badge label="Pending" tone="warn" />}</div>)}</div></section>
          <section className="card"><div className="ch"><h2>Allocation requests</h2><span className="count-badge">{pendingRequests.length}</span></div><div className="cb">{!pendingRequests.length && <p className="hint">No pending allocations</p>}{pendingRequests.map((r) => <div className="request-card" key={r.requestId}><div><b>{displayUser(r.userId)} · {r.workerIds.length} Worker(s)</b><small>{r.reason}</small></div>{admin ? <div className="acts"><button className="btn accent" disabled={working} onClick={() => void run(() => decide.mutateAsync({ requestId: r.requestId, decision: "APPROVE" }), "Allocation approved.")}>Approve</button><button className="btn" disabled={working} onClick={() => void run(() => decide.mutateAsync({ requestId: r.requestId, decision: "REJECT" }), "Allocation rejected.")}>Reject</button></div> : <Badge label="Pending" tone="warn" />}</div>)}</div></section>
        </div>}
      </>}
      {panel === "members" && <>
        <div className="role-toolbar"><div><span className="section-eyebrow">MEMBERSHIP</span><h2>Members</h2></div>{admin && <button className="btn violet" onClick={() => open("invite")}>Invite by email</button>}</div>
        <div className="member-grid">{data?.members.map((m) => <section className="member-card" key={m.user.userId}><span className={`member-avatar ${m.role.toLowerCase()}`}>{m.user.displayName.slice(0, 1)}</span><div><b>{m.user.displayName}</b><small>{m.user.email || `${m.user.username}@example.test`}</small></div><span className={`role-pill ${m.role.toLowerCase()}`}>{m.role === "ADMIN" ? "Admin" : "Participant"}</span></section>)}</div>
        {!!data?.invitations.length && <section className="card"><div className="ch"><h2>Invitations</h2></div><div className="cb">{data.invitations.map((i) => <div className="request-card" key={i.invitationId}><div><b>{i.email}</b><small>{new Date(i.createdAt).toLocaleString()}</small></div><Badge label={i.status === "PENDING" ? "Awaiting confirmation" : "Accepted"} tone={i.status === "PENDING" ? "warn" : "ok"} /></div>)}</div></section>}
      </>}
      {panel === "activity" && <section className="card"><div className="ch"><h2>Activity</h2></div><div className="cb activity-stream">{audit.isError && <p role="alert">Activity unavailable</p>}{!audit.data?.length && !audit.isError && <p className="hint">No activity</p>}{audit.data?.slice(0, 25).map((a) => <div key={a.auditId}><span className="activity-dot" /><div><b>{a.action.replaceAll("POOL", "RESOURCE").replaceAll("_", " ")}</b><small>{displayUser(a.actorUserId)} · {new Date(a.createdAt).toLocaleString()}</small></div></div>)}</div></section>}
      {admin && <div className="workspace-settings"><span>Workspace settings</span><button className="link" onClick={() => setConfirmation({ title: "Delete workspace", detail: workspace.name + ". Active experiments and allocations must be stopped first.", action: async () => { await deleteWorkspace.mutateAsync(workspace.workspaceId); await refreshSession(); navigate("/workspace"); } })}>Delete workspace</button></div>}
    </QueryState>
    {dialog === "apply" && <Modal title="Apply Worker" subtitle={workspace.name} onClose={() => setDialog(null)}><form className="modal-form" onSubmit={(e) => { e.preventDefault(); if (canApply && ownSelected) void run(() => submit.mutateAsync({ workspaceId: workspace.workspaceId, workerId: ownSelected.workerId }), admin ? "Worker added to Resources." : "Admission request submitted.", () => setDialog(null)); }}>
      <p className="hint">Select one of your Workers registered in the Workers tab. To register a new Worker, go to Workers.</p>
      <p className="hint">{admin ? "Resource admission: direct" : "Resource admission: Admin approval required"}</p>
      {owned.isError || submissions.isError ? <p role="alert">Worker registry unavailable</p> : owned.isPending || submissions.isPending ? <p>Loading Workers…</p> : !ownAvailable.length ? <div className="empty"><b>No eligible Workers</b><span>Register a Worker in the Workers tab. Workers already connected or awaiting approval cannot be applied.</span></div> : <div className="worker-picker">{ownAvailable.map((w) => <label className={ownSelected?.workerId === w.workerId ? "selected" : ""} key={w.workerId}><input type="radio" name="owned-worker" checked={ownSelected?.workerId === w.workerId} onChange={() => setOwnedId(w.workerId)} /><ChipIcon /><span><b>{w.profile.gpuName}</b><small>{w.profile.vramTotalMb / 1024} GiB · Registered</small><small className="mono">{w.workerId}</small></span></label>)}</div>}
      {error && <p className="note err" role="alert">{error}</p>}
      <div className="modal-footer"><Link className="btn" to="/workers">Go to Workers</Link><button className="btn" type="button" onClick={() => setDialog(null)}>Cancel</button><button className={`btn ${admin ? "violet" : "accent"}`} disabled={!canApply}>{working ? "Applying…" : "Apply"}</button></div>
    </form></Modal>}
    {dialog === "request" && <Modal title="Request Workers" subtitle={workspace.name} onClose={() => setDialog(null)}><form className="modal-form" onSubmit={(e) => { e.preventDefault(); const ids = selectedWorkers.filter((id) => available.some((w) => w.workerId === id)); if (ids.length) void run(() => request.mutateAsync({ workerIds: ids, reason }), "Allocation request submitted.", () => { setDialog(null); setSelectedWorkers([]); setReason(""); }); }}>
      <div className="worker-picker">{available.map((w) => <label className={selectedWorkers.includes(w.workerId) ? "selected" : ""} key={w.workerId}><input type="checkbox" checked={selectedWorkers.includes(w.workerId)} onChange={() => setSelectedWorkers((ids) => ids.includes(w.workerId) ? ids.filter((id) => id !== w.workerId) : [...ids, w.workerId])} /><span><b>{w.profile.gpuName}</b><small>{w.profile.vramTotalMb / 1024} GiB · Available</small></span></label>)}</div>
      <label className="fg">Purpose<textarea className="inp" required maxLength={1000} value={reason} onChange={(e) => setReason(e.target.value)} /></label>{error && <p className="note err" role="alert">{error}</p>}
      <div className="modal-footer"><button className="btn" type="button" onClick={() => setDialog(null)}>Cancel</button><button className="btn accent" disabled={working || !selectedWorkers.some((id) => available.some((w) => w.workerId === id))}>Submit request</button></div>
    </form></Modal>}
    {dialog === "invite" && <Modal title="Invite member" subtitle="Email invitation" onClose={() => setDialog(null)}>{invited ? <div className="modal-form"><div className="invitation-success">✓</div><h3>Invitation created</h3><p>{email}</p><Badge label="Awaiting recipient confirmation" tone="warn" /><p className="hint">Local simulation · No email sent. Recipient confirmation is available in Profile.</p><div className="modal-footer"><button className="btn accent" onClick={() => setDialog(null)}>Done</button></div></div> : <form className="modal-form" onSubmit={(e) => { e.preventDefault(); void run(() => invite.mutateAsync({ workspaceId: workspace.workspaceId, email }), "Invitation created.", () => setInvited(true)); }}>
      <label className="fg">Email address<input type="email" className="inp" autoFocus required maxLength={254} placeholder="name@example.com" value={email} onChange={(e) => setEmail(e.target.value)} /></label><div className="invitation-preview"><span className="section-eyebrow">INVITATION PREVIEW</span><h3>{workspace.name}</h3><p>Role: Participant</p><span>Membership remains pending until confirmation.</span></div>
      {error && <p className="note err" role="alert">{error}</p>}<p className="hint">Local simulation · No outgoing email.</p><div className="modal-footer"><button className="btn" type="button" onClick={() => setDialog(null)}>Cancel</button><button className="btn violet" disabled={working}>{working ? "Creating…" : "Send invitation"}</button></div>
    </form>}</Modal>}
    {confirmation && <Modal title={confirmation.title} onClose={() => setConfirmation(null)}><div className="modal-form"><p>{confirmation.detail}</p>{error && <p className="note err" role="alert">{error}</p>}<div className="modal-footer"><button className="btn" onClick={() => setConfirmation(null)}>Cancel</button><button className="btn dng" disabled={working} onClick={() => void run(confirmation.action, "Request accepted.", () => setConfirmation(null))}>Confirm</button></div></div></Modal>}
  </>;
}
