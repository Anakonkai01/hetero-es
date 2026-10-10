import { Link } from "react-router";
import { useSession } from "../app/session";
import { useAudit, useModels, useResources } from "../hooks/useAccess";
import { useWorkers } from "../hooks/useWorkers";
import { PageHeader } from "../components/ui/PageHeader";
import { QueryState } from "../components/common/QueryState";
import { WorkerMetrics } from "../components/workspace/WorkerMetrics";

export function RuntimeWorkspacePage() {
  const { workspace } = useSession(); const resources = useResources(); const workers = useWorkers(); const audit = useAudit();
  return <><div className={`workspace-hero ${workspace?.role === "ADMIN" ? "admin" : "participant"}`}><div className="workspace-hero-heading"><div><h1>{workspace?.name}</h1><p>Shared GPU pool · persistent FIFO queue · one active experiment</p></div><span className="role-pill">{workspace?.role}</span></div><div className="workspace-hero-footer"><Link className="btn accent" to="/experiments/new">Create experiment</Link><Link className="btn" to="/experiments">Experiments</Link></div></div>
    <QueryState isPending={resources.isPending || workers.isPending} isError={resources.isError || workers.isError} hasData={Boolean(resources.data && workers.data)} title="Workspace resources unavailable">
      <RuntimeWorkerCards />
      <section className="card"><div className="ch"><h2>Resource management</h2></div><div className="cb demo-form"><div className="acts"><button className="btn" disabled title="The configured pool is shared; the queue reserves workers automatically">Request workers</button><button className="btn" disabled title="Worker hosts are configured by the administrator">Apply worker</button><button className="btn" disabled title="Member management is not implemented">Invite member</button></div><p className="hint">Both accounts can submit runs. Admin sees and can cancel all experiments; Participant sees only their own experiments.</p></div></section>
      <section className="card"><div className="ch"><h2>Members</h2></div><div className="cb">{resources.data?.members.map((member) => <p key={member.user.userId}>{member.user.displayName} · {member.role}</p>)}</div></section>
      <section className="card"><div className="ch"><h2>Activity</h2></div><div className="cb">{audit.isError && <p role="alert">Activity unavailable</p>}{audit.data?.slice(0, 20).map((entry) => <p key={entry.auditId}>{entry.action} · {entry.actorUserId} · {new Date(entry.createdAt).toLocaleString()}</p>)}</div></section>
    </QueryState></>;
}

function RuntimeWorkerCards() {
  const workers = useWorkers();
  return <QueryState isPending={workers.isPending} isError={workers.isError} hasData={Boolean(workers.data)} title="Worker registry unavailable"><div className="resource-grid">{workers.data?.map((worker) => <section className="card" key={worker.workerId}><div className="ch"><h2>{worker.profile.gpuName}</h2><span className={`connection-tag ${worker.status.toLowerCase()}`}>{worker.status}</span></div><div className="cb demo-form"><Link className="link mono" to={`/workers/${worker.workerId}`}>{worker.workerId}</Link>{worker.status === "ONLINE" ? <WorkerMetrics worker={worker} /> : <p>GPU metrics unavailable</p>}<p>{worker.admissionReason}</p><p>Allocation: {worker.allocatedTo ?? "Available"}</p></div></section>)}</div></QueryState>;
}

export function RuntimeWorkersPage() {
  return <><PageHeader title="Workers" description="Live probes of administrator-configured hosts." actions={<button className="btn" disabled title="Add hosts in the private runtime configuration">Register worker</button>} /><RuntimeWorkerCards /></>;
}

export function RuntimeModelsPage() {
  const models = useModels();
  return <><PageHeader title="Models" description="Pinned runtime model" /><QueryState isPending={models.isPending} isError={models.isError} hasData={Boolean(models.data)} title="Model capabilities unavailable"><section className="card"><div className="cb demo-form">{models.data?.map((model) => <div key={model.modelArtifactId}><h2>{model.name}</h2><p className="mono">{model.revision}</p></div>)}<button className="btn" disabled title="Only the pinned Qwen checkpoint is supported">Register / upload model</button><Link className="btn pri" to="/experiments/new">Create experiment</Link></div></section></QueryState></>;
}

export function RuntimeProfilePage() {
  const { session, workspace } = useSession();
  return <><PageHeader title="Profile" /><section className="card"><div className="cb demo-form"><h2>{session?.user.displayName}</h2><p>{session?.user.username} · {workspace?.role}</p><p>{workspace?.name}</p><button className="btn" disabled title="Account details are managed through the private deployment configuration">Edit profile</button><button className="btn" disabled title="Member management is not implemented">Manage invitations</button></div></section></>;
}
