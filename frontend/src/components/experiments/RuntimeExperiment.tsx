import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { apiGet, downloadArtifact } from "../../api/client";
import { archiveExperiment, requestExperimentCancel, submitExperiment, updateExperiment } from "../../api/experiments";
import { useSession, useScopeKey } from "../../app/session";
import { useAccessMutation } from "../../hooks/useAccess";
import { useWorkers } from "../../hooks/useWorkers";
import { useGenerations } from "../../hooks/useGenerations";
import { useArtifacts } from "../../hooks/useArtifacts";
import type { CreateExperimentRequest, Experiment } from "../../types/experiment";
import { RewardChart } from "./RewardChart";

interface Capabilities { modelId: string; modelRevision: string; workloads: string[]; schedulerPolicies: string[]; syncModes: string[]; workerIds: string[] }
export function RuntimeConfiguration({ initial, onSave, pending }: { initial?: Experiment; onSave: (value: CreateExperimentRequest) => Promise<unknown>; pending: boolean }) {
  const scope = useScopeKey(); const workers = useWorkers();
  const cap = useQuery({ queryKey: ["capabilities", ...scope], queryFn: () => apiGet<Capabilities>("/api/v1/capabilities"), enabled: scope.every(Boolean) });
  const [name, setName] = useState(initial?.name ?? "");
  const [task, setTask] = useState(initial?.task ?? "arith16");
  const [generations, setGenerations] = useState(initial?.maxGenerations ?? 3);
  const [candidates, setCandidates] = useState(initial?.candidatesPerGeneration ?? 8);
  const [alpha, setAlpha] = useState(initial?.alpha ?? .001);
  const [sigma, setSigma] = useState(initial?.sigma ?? .001);
  const [decoder, setDecoder] = useState(initial?.decodeEngine ?? "hf_generate");
  const [selected, setSelected] = useState<string[]>(initial?.workerIds ?? []);
  const [error, setError] = useState("");
  const available = workers.data ?? [];
  return <form className="cb demo-form" onSubmit={(event) => {
    event.preventDefault(); setError("");
    if (!cap.data || !selected.length) { setError("Select at least one configured worker."); return; }
    void onSave({ name, modelName: cap.data.modelId, modelArtifactId: "qwen-pinned", task,
      maxGenerations: generations, candidatesPerGeneration: candidates, alpha, sigma, decodeEngine: decoder,
      workerIds: selected, schedulerPolicy: "greedy", syncMode: "synchronous" }).catch((e: Error) => setError(e.message));
  }}>
    <p>Shared GPU pool · FIFO · one active experiment. Runs stop after 30 minutes.</p>
    {cap.isError && <p className="note err" role="alert">Runtime capabilities unavailable. Check the control service.</p>}
    <label className="fg">Experiment name<input className="inp" required minLength={3} maxLength={160} value={name} onChange={(e) => setName(e.target.value)} /></label>
    <label className="fg">Model<input className="inp" disabled value={cap.data?.modelId ?? "Loading…"} /></label>
    <p className="hint">Pinned revision: {cap.data?.modelRevision}</p>
    <label className="fg">Workload<select className="sel" value={task} onChange={(e) => setTask(e.target.value)}>{cap.data?.workloads.map((value) => <option key={value}>{value}</option>)}</select></label>
    <label className="fg">Decoder<select className="sel" value={decoder} onChange={(e) => setDecoder(e.target.value)}><option>hf_generate</option><option>hf_compact</option></select></label>
    <p className="hint">FP32 evaluation · canonical CPU noise · exact worker restore.</p>
    <label className="fg">Maximum generations<input className="inp" type="number" min={1} max={1000} required value={generations} onChange={(e) => setGenerations(Number(e.target.value))} /></label>
    <label className="fg">Candidates per generation<input className="inp" type="number" min={2} max={256} required value={candidates} onChange={(e) => setCandidates(Number(e.target.value))} /></label>
    <label className="fg">Alpha<input className="inp" type="number" min={.0000001} max={1} step="any" required value={alpha} onChange={(e) => setAlpha(Number(e.target.value))} /></label>
    <label className="fg">Sigma<input className="inp" type="number" min={.0000001} max={1} step="any" required value={sigma} onChange={(e) => setSigma(Number(e.target.value))} /></label>
    <label className="fg">Scheduling<select className="sel" value="greedy" disabled><option>greedy</option><option disabled>capacity-weighted (not configured)</option><option disabled>round-robin (not configured)</option></select></label>
    <label className="fg">Synchronization<select className="sel" value="synchronous" disabled><option>synchronous</option><option disabled>asynchronous (unsupported)</option></select></label>
    <fieldset><legend>Configured workers</legend>{workers.isError && <p role="alert">Worker status unavailable</p>}{available.map((worker) => <label className="demo-check" key={worker.workerId}><input type="checkbox" checked={selected.includes(worker.workerId)} onChange={() => setSelected((ids) => ids.includes(worker.workerId) ? ids.filter((id) => id !== worker.workerId) : [...ids, worker.workerId])} />{worker.profile.gpuName} · {worker.workerId} · {worker.status}</label>)}</fieldset>
    <p className="hint">Selected workers are started automatically. An unavailable selected worker is reported; the run may continue with the other selected workers.</p>
    <label className="fg">Upload dataset<input type="file" disabled /></label><span className="hint">Built-in workloads only; dataset upload is unsupported.</span>
    <button type="button" className="btn" disabled title="Only the pinned model is supported">Upload model</button>
    {error && <p className="note err" role="alert">{error}</p>}
    <button className="btn pri" disabled={pending || !cap.data}>Save draft</button>
  </form>;
}

export function RuntimeControls({ experiment: e }: { experiment: Experiment }) {
  const { session, workspace } = useSession(); const navigate = useNavigate();
  const submit = useAccessMutation(submitExperiment); const cancel = useAccessMutation(requestExperimentCancel);
  const archive = useAccessMutation(archiveExperiment); const edit = useAccessMutation(updateExperiment);
  const [editing, setEditing] = useState(false);
  const permitted = e.ownerUserId === session?.user.userId || workspace?.role === "ADMIN";
  const terminal = ["COMPLETED", "CANCELLED", "FAILED", "DRAFT"].includes(e.status);
  const error = submit.error ?? cancel.error ?? archive.error ?? edit.error;
  const busy = submit.isPending || cancel.isPending || archive.isPending || edit.isPending;
  return <section className="card"><div className="ch"><h2>Experiment management</h2></div><div className="cb demo-form">
    <p>Selected workers: {e.workerIds?.join(", ")}</p>
    {e.failureReason && <p className="note err" role="alert">{e.failureReason}</p>}
    {error && <p className="note err" role="alert">{error.message}</p>}
    {permitted && <div className="acts">
      {e.status === "DRAFT" && <><button className="btn" disabled={busy} onClick={() => setEditing(!editing)}>Edit configuration</button><button className="btn pri" disabled={busy} onClick={() => void submit.mutateAsync(e.experimentId).catch(() => {})}>Start experiment</button></>}
      {!terminal && !e.cancelRequested && <button className="btn dng" disabled={busy} onClick={() => void cancel.mutateAsync(e.experimentId).catch(() => {})}>Cancel experiment</button>}
      <button className="btn" disabled title="Pause and resume require checkpoint lifecycle support beyond cancellation">Pause / resume</button>
      <button className="btn" disabled title="Worker selection is immutable after submission">Change workers during run</button>
      {terminal && <button className="btn dng" disabled={busy} onClick={() => { if (window.confirm("Archive this experiment and retain its evidence?")) void archive.mutateAsync(e.experimentId).then(() => navigate("/experiments")).catch(() => {}); }}>Archive</button>}
    </div>}
    {e.cancelRequested && !terminal && <p className="note">Stopping new leases; waiting for current candidates to restore and all selected workers to stop. The last completed checkpoint is retained.</p>}
    {editing && e.status === "DRAFT" && <RuntimeConfiguration initial={e} pending={edit.isPending} onSave={async (configuration) => { await edit.mutateAsync({ experimentId: e.experimentId, configuration }); setEditing(false); }} />}
  </div></section>;
}

export function RuntimeResults({ experiment: e }: { experiment: Experiment }) {
  const generations = useGenerations(e.experimentId); const artifacts = useArtifacts();
  const [error, setError] = useState(""); const [downloading, setDownloading] = useState("");
  return <section className="card"><div className="ch"><h2>Runtime results</h2><small>Measured candidate rewards from the runtime ledger</small></div><div className="cb demo-form">
    <p>Completed generations: {e.completedGenerations ?? 0}/{e.maxGenerations} · Committed candidates in the current generation: {e.committedCandidateCount ?? 0}/{e.candidatesPerGeneration}</p>
    <RewardChart generations={generations.data ?? []} />
    <p className="hint">Validation and test scores are unavailable: this run evaluates candidate rewards on the selected built-in workload.</p>
    {error && <p role="alert" className="note err">{error}</p>}
    {artifacts.data?.filter((a) => a.experimentId === e.experimentId).map((artifact) => <div className="demo-item" key={artifact.artifactId}><span>{artifact.name} · {artifact.sizeBytes?.toLocaleString()} bytes</span><button className="btn" disabled={Boolean(downloading)} onClick={() => {
      setError(""); setDownloading(artifact.artifactId);
      void downloadArtifact(artifact.artifactId, artifact.name).catch((e: Error) => setError(e.message)).finally(() => setDownloading(""));
    }}>{downloading === artifact.artifactId ? "Downloading…" : "Download"}</button></div>)}
    <p className="hint">A checkpoint download contains canonical raw FP16 weights. Load it with Track A's schema and verified hash; it is not a standalone Hugging Face model directory.</p>
  </div></section>;
}
