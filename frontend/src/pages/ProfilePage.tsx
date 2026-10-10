import { useState } from "react";
import { useSession } from "../app/session";
import { updateProfile, acceptInvitation } from "../api/access";
import { useAccessMutation, useMyWorkers, useMyInvitations } from "../hooks/useAccess";
import { PageHeader } from "../components/ui/PageHeader";

export function ProfilePage() { return IS_MOCK ? <MockProfilePage /> : <RuntimeProfilePage />; }

function MockProfilePage() {
  const { session, refreshSession } = useSession();
  const user = session!.user;
  const workers = useMyWorkers();
  const invitations = useMyInvitations();
  const accept = useAccessMutation(acceptInvitation);
  const save = useAccessMutation(updateProfile);
  const [displayName, setName] = useState(user.displayName);
  const [email, setEmail] = useState(user.email ?? "");
  const [bio, setBio] = useState(user.bio ?? "");
  return <><PageHeader title="Profile" description="Account details and workspace memberships." />
    <section className="card"><div className="ch"><h2>{user.username}</h2></div>
      <form className="cb demo-form" onSubmit={(e) => { e.preventDefault(); void save.mutateAsync({ displayName, email, bio }).then(refreshSession).catch(() => {}); }}>
        <label className="fg">Display name<input className="inp" required maxLength={160} value={displayName} onChange={(e) => setName(e.target.value)} /></label>
        <label className="fg">Email<input className="inp" type="email" maxLength={254} value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        <label className="fg">About you<textarea className="inp" maxLength={1000} value={bio} onChange={(e) => setBio(e.target.value)} /></label>
        {save.error && <p role="alert">{save.error.message}</p>}
        {save.isSuccess && <p role="status">Profile saved.</p>}
        <button className="btn pri" disabled={save.isPending}>Save profile</button>
      </form></section>
    <section className="card"><div className="ch"><h2>Workspace invitations</h2><small>Email confirmation · Local simulation</small></div><div className="cb">
      {invitations.isError && <p role="alert">Invitations unavailable</p>}
      {invitations.isPending && <p className="hint">Loading invitations…</p>}
      {!invitations.isPending && !invitations.isError && !invitations.data?.length && <p className="hint">No invitations</p>}
      {invitations.data?.map((i) => <div className="request-card" key={i.invitationId}><div><b>{i.workspaceName}</b><small>{i.email} · {i.status === "PENDING" ? "Awaiting confirmation" : "Accepted"}</small></div>{i.status === "PENDING" && <button className="btn accent" disabled={accept.isPending} onClick={() => void accept.mutateAsync(i.invitationId).then(refreshSession).catch(() => {})}>Confirm and join</button>}</div>)}
      {accept.error && <p className="note err" role="alert">{accept.error.message}</p>}
    </div></section>
    <section className="card"><div className="ch"><h2>Memberships and resources</h2></div><div className="cb demo-form">
      <p>{session!.workspaces.length} workspaces · {workers.data?.length ?? 0} owned Workers</p>
      {session!.workspaces.map((w) => <div key={w.workspaceId}>{w.name} · Role: {w.role}</div>)}
    </div></section></>;
}
import { IS_MOCK } from "../lib/dataSource";
import { RuntimeProfilePage } from "./RuntimePages";
