import { useState } from "react";
import { Link } from "react-router";
import { apiPost } from "../api/client";
import { useSession } from "../app/session";
import { useAccessMutation } from "../hooks/useAccess";
import { PageHeader } from "../components/ui/PageHeader";
import { Modal } from "../components/ui/Modal";
import { DashboardIcon, PlusIcon } from "../components/ui/Icons";
import { IS_MOCK } from "../lib/dataSource";

export function WorkspaceListPage() {
  const { session, selectWorkspace, refreshSession } = useSession();
  const [name, setName] = useState(""); const [description, setDescription] = useState("");
  const [view, setView] = useState("grid"); const [creating, setCreating] = useState(false);
  const create = useAccessMutation((input: { name: string; description: string }) => apiPost("/api/v1/workspaces", input));
  const workspaces = session?.workspaces ?? [];
  return <>
    <PageHeader title="Workspaces" description="Shared compute resources and memberships." actions={<button className="btn accent" disabled={!IS_MOCK} title={IS_MOCK ? undefined : "This deployment uses the configured HeteroES Lab workspace"} onClick={() => { create.reset(); setCreating(true); }}><PlusIcon />Create workspace</button>} />
    <div className="workspace-summary-strip"><span><b>{workspaces.length}</b> workspaces</span><span><b>{workspaces.filter((w) => w.role === "ADMIN").length}</b> administered</span><div className="view-toggle"><button aria-pressed={view === "grid"} className={view === "grid" ? "selected" : ""} onClick={() => setView("grid")}>Grid</button><button aria-pressed={view === "list"} className={view === "list" ? "selected" : ""} onClick={() => setView("list")}>List</button></div></div>
    <div className={`workspace-collection ${view}`}>{workspaces.map((w) => <Link className={`workspace-tile ${w.role === "ADMIN" ? "admin" : "participant"}`} key={w.workspaceId} to={`/workspace/${w.workspaceId}`} onClick={() => selectWorkspace(w.workspaceId)}>
      <div className="workspace-tile-top"><span className="workspace-emblem"><DashboardIcon /></span><span className={`role-pill ${w.role.toLowerCase()}`}>Role: {w.role === "ADMIN" ? "Admin" : "Participant"}</span></div>
      <div className="workspace-tile-body"><h2>{w.name}</h2><p>{w.description || "Shared compute workspace"}</p></div>
      <div className="workspace-tile-bottom"><span>Created by {w.creatorUserId === session?.user.userId ? session?.user.displayName : w.creatorUserId?.replace(/^user-/, "") ?? "—"}</span><span>Open ↗</span></div>
    </Link>)}</div>
    {!workspaces.length && <div className="empty"><b>No workspaces</b></div>}
    {creating && <Modal title="Create workspace" subtitle="Workspace details" onClose={() => setCreating(false)}><form className="modal-form" onSubmit={(e) => { e.preventDefault(); void create.mutateAsync({ name, description }).then(async () => { await refreshSession(); setCreating(false); setName(""); setDescription(""); }).catch(() => {}); }}>
      <label className="fg">Name<input className="inp" autoFocus required maxLength={160} placeholder="Workspace name" value={name} onChange={(e) => setName(e.target.value)} /></label>
      <label className="fg">Description<textarea className="inp" maxLength={1000} placeholder="Optional description" value={description} onChange={(e) => setDescription(e.target.value)} /></label>
      {create.error && <p className="note err" role="alert">{create.error.message}</p>}
      <div className="modal-footer"><button className="btn" type="button" onClick={() => setCreating(false)}>Cancel</button><button className="btn accent" disabled={create.isPending}>{create.isPending ? "Creating…" : "Create workspace"}</button></div>
    </form></Modal>}
  </>;
}
