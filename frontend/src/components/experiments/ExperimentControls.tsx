import { useState } from "react";
import { useNavigate } from "react-router";
import { archiveExperiment, submitExperiment, updateExperiment, requestExperimentCancel, controlExperiment } from "../../api/experiments";
import { useSession } from "../../app/session";
import { useAccessMutation, useResources } from "../../hooks/useAccess";
import { useWorkers } from "../../hooks/useWorkers";
import type { Experiment } from "../../types/experiment";
import { ExperimentConfiguration } from "./ExperimentConfiguration";

export function ExperimentControls(props: { experiment: Experiment }) { return IS_MOCK ? <MockExperimentControls {...props} /> : <RuntimeControls {...props} />; }

function MockExperimentControls({ experiment: e }: { experiment: Experiment }) {
  const { session } = useSession(); const navigate = useNavigate();
  const submit = useAccessMutation(submitExperiment); const archive = useAccessMutation(archiveExperiment);
  const update = useAccessMutation(updateExperiment); const control = useAccessMutation(controlExperiment); const cancel = useAccessMutation(requestExperimentCancel);
  const resources = useResources(); const workers = useWorkers();
  const [editing, setEditing] = useState(false); const [workerIds, setWorkerIds] = useState(e.workerIds ?? []);
  const own = e.ownerUserId === session?.user.userId;
  const granted = resources.data?.grants.filter((g) => g.userId === session?.user.userId && g.status === "ACTIVE").flatMap((g) => g.workerIds) ?? [];
  const error = submit.error ?? archive.error ?? update.error ?? control.error ?? cancel.error;
  const busy = submit.isPending || archive.isPending || update.isPending || control.isPending || cancel.isPending;
  const act = (action: "PAUSE" | "RESUME" | "CHANGE_WORKERS") => { void control.mutateAsync({ experimentId: e.experimentId, action, workerIds }).catch(() => {}); };
  return <section className="card"><div className="ch"><h2>Experiment management</h2></div><div className="cb demo-form">
    <p>Workers: {e.workerIds?.join(", ") || "None"}</p>
    {error && <div className="note err" role="alert">{error.message}</div>}
    {own && <div className="acts">
      {e.status === "DRAFT" && <><button className="btn" onClick={() => setEditing(!editing)}>Edit configuration</button><button className="btn pri" disabled={busy} onClick={() => void submit.mutateAsync(e.experimentId).catch(() => {})}>Start experiment</button></>}
      {e.status === "RUNNING" && !e.cancelRequested && <button className="btn" disabled={busy || !e.maxGenerations} onClick={() => act("PAUSE")}>Pause after current generation</button>}
      {e.status === "PAUSED" && <button className="btn pri" disabled={busy} onClick={() => act("RESUME")}>Resume</button>}
      {["RUNNING", "QUEUED", "PAUSING", "PAUSED"].includes(e.status) && !e.cancelRequested && <button className="btn dng" disabled={busy} onClick={() => { if (window.confirm("Cancel this experiment?")) void cancel.mutateAsync(e.experimentId).catch(() => {}); }}>Cancel experiment</button>}
      {!["RUNNING", "QUEUED", "PAUSING", "PAUSED"].includes(e.status) && <button className="btn dng" disabled={busy} onClick={() => { if (window.confirm("Archive this experiment and retain its history?")) void archive.mutateAsync(e.experimentId).then(() => navigate("/experiments")).catch(() => {}); }}>Delete / archive</button>}
    </div>}
    {e.status === "PAUSING" && <div className="note">Finishing the current generation, then saving state. No next generation will start.</div>}
    {e.checkpointSavedAt && <span className="hint">Demo checkpoint state saved: {new Date(e.checkpointSavedAt).toLocaleString()}</span>}
    {own && e.status === "PAUSED" && <fieldset><legend>Change Workers for the next generation</legend>{workers.data?.filter((w) => granted.includes(w.workerId)).map((w) => <label className="demo-check" key={w.workerId}><input type="checkbox" checked={workerIds.includes(w.workerId)} onChange={() => setWorkerIds((ids) => ids.includes(w.workerId) ? ids.filter((id) => id !== w.workerId) : [...ids, w.workerId])} />{w.profile.gpuName} · {w.workerId}</label>)}<button className="btn" disabled={busy || !workerIds.length} onClick={() => act("CHANGE_WORKERS")}>Save Workers</button></fieldset>}
    {editing && own && e.status === "DRAFT" && <ExperimentConfiguration initial={e} pending={update.isPending} onSave={async (configuration) => { await update.mutateAsync({ experimentId: e.experimentId, configuration }); setEditing(false); }} />}
  </div></section>;
}
import { IS_MOCK } from "../../lib/dataSource";
import { RuntimeControls } from "./RuntimeExperiment";
