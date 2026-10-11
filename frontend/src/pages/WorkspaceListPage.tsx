import {useProduct} from '@heteroes/product-ui';
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
  const {t}=useProduct();
  const { session, selectWorkspace, refreshSession } = useSession();
  const [name, setName] = useState(""); const [description, setDescription] = useState("");
  const [view, setView] = useState("grid"); const [creating, setCreating] = useState(false);
  const create = useAccessMutation((input: { name: string; description: string }) => apiPost("/api/v1/workspaces", input));
  const workspaces = session?.workspaces ?? [];
  return <>
    <PageHeader title={t("Workspaces")} description={t("Shared compute resources and memberships.")} actions={<button className="btn accent" disabled={!IS_MOCK && (session?.user.accountStatus !== "ACTIVE" || !session.user.canCreateWorkspace)} title={!IS_MOCK && !session?.user.canCreateWorkspace ? t("A platform administrator must grant workspace creation permission") : undefined} onClick={() => { create.reset(); setCreating(true); }}><PlusIcon />{t("Create workspace")}</button>} />
    {!IS_MOCK && session?.user.accountStatus !== "ACTIVE" && <div className="note warn" role="status">{t("Account status:")}{session?.user.accountStatus}{t(". A platform administrator must approve your account before you can access lab resources. You can edit your")}<Link to="/profile">{t("profile")}</Link>.</div>}
    {!IS_MOCK && session?.user.accountStatus === "ACTIVE" && !workspaces.length && <p>{t("Join a workspace from the invitations on your")}<Link to="/profile">{t("profile")}</Link>{t(", or request permission to create one.")}</p>}
    <div className="workspace-summary-strip"><span><b>{workspaces.length}</b> {t("workspaces")}</span><span><b>{workspaces.filter((w) => w.role === "ADMIN").length}</b> {t("administered")}</span><div className="view-toggle"><button aria-pressed={view === "grid"} className={view === "grid" ? "selected" : ""} onClick={() => setView("grid")}>{t("Grid")}</button><button aria-pressed={view === "list"} className={view === "list" ? "selected" : ""} onClick={() => setView("list")}>{t("List")}</button></div></div>
    <div className={`workspace-collection ${view}`}>{workspaces.map((w) => <Link className={`workspace-tile ${w.role === "ADMIN" ? "admin" : "participant"}`} key={w.workspaceId} to={`/workspace/${w.workspaceId}`} onClick={() => selectWorkspace(w.workspaceId)}>
      <div className="workspace-tile-top"><span className="workspace-emblem"><DashboardIcon /></span><span className={`role-pill ${w.role.toLowerCase()}`}>{t("Role:")}{w.role === "ADMIN" ? "Admin" : "Participant"}</span></div>
      <div className="workspace-tile-body"><h2>{w.name}</h2><p>{w.description || "Shared compute workspace"}</p></div>
      <div className="workspace-tile-bottom"><span>{t("Created by")}{w.creatorUserId === session?.user.userId ? session?.user.displayName : w.creatorUserId?.replace(/^user-/, "") ?? "—"}</span><span>{t("Open ↗")}</span></div>
    </Link>)}</div>
    {!workspaces.length && <div className="empty"><b>{t("No workspaces")}</b></div>}
    {creating && <Modal title={t("Create workspace")} subtitle="Workspace details" onClose={() => setCreating(false)}><form className="modal-form" onSubmit={(e) => { e.preventDefault(); void create.mutateAsync({ name, description }).then(async () => { await refreshSession(); setCreating(false); setName(""); setDescription(""); }).catch(() => {}); }}>
      <label className="fg">{t("Name")}<input className="inp" autoFocus required minLength={3} maxLength={100} placeholder={t("Workspace name")} value={name} onChange={(e) => setName(e.target.value)} /></label>
      <label className="fg">{t("Description")}<textarea className="inp" maxLength={1000} placeholder={t("Optional description")} value={description} onChange={(e) => setDescription(e.target.value)} /></label>
      {create.error && <p className="note err" role="alert">{create.error.message}</p>}
      <div className="modal-footer"><button className="btn" type="button" onClick={() => setCreating(false)}>{t("Cancel")}</button><button className="btn accent" disabled={create.isPending}>{create.isPending ? t("Creating…") : t("Create workspace")}</button></div>
    </form></Modal>}
  </>;
}
