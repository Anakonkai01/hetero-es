import {useProduct,StepHeader} from '@heteroes/product-ui';
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { apiGet, apiPatch, downloadArtifact } from "../../api/client";
import { archiveExperiment, requestExperimentCancel, submitExperiment, updateExperiment } from "../../api/experiments";
import { useSession, useScopeKey } from "../../app/session";
import { useAccessMutation } from "../../hooks/useAccess";
import { useWorkers } from "../../hooks/useWorkers";
import { useGenerations } from "../../hooks/useGenerations";
import { useArtifacts } from "../../hooks/useArtifacts";
import type { CreateExperimentRequest, Experiment } from "../../types/experiment";
import { RewardChart } from "./RewardChart";

interface Capabilities { agentMode?:boolean;coordinatorDevices?:{deviceId:string;workerId:string}[]; modelId: string; modelRevision: string; workloads: string[]; schedulerPolicies: string[]; syncModes: string[]; workerIds: string[] }
export function RuntimeConfiguration({ initial, onSave, pending }: { initial?: Experiment; onSave: (value: CreateExperimentRequest) => Promise<unknown>; pending: boolean }) {
  const {t}=useProduct(); const [step,setStep]=useState(0);
  const scope=useScopeKey(); const workers=useWorkers();
  const cap=useQuery({queryKey:["capabilities",...scope],queryFn:()=>apiGet<Capabilities>("/api/v1/capabilities"),enabled:scope.every(Boolean)});
  const [name,setName]=useState(initial?.name??""); const [task,setTask]=useState(initial?.task??"arith16");
  const [generations,setGenerations]=useState(initial?.maxGenerations??3); const [candidates,setCandidates]=useState(initial?.candidatesPerGeneration??8);
  const [alpha,setAlpha]=useState(initial?.alpha??.001);const [sigma,setSigma]=useState(initial?.sigma??.001);
  const [decoder,setDecoder]=useState(initial?.decodeEngine??"hf_generate");const [selected,setSelected]=useState<string[]>(initial?.workerIds??[]);
  const [coordinator,setCoordinator]=useState(initial?.coordinatorDeviceId??"");const [interval,setInterval]=useState(initial?.backupPolicy?.interval??1);const [retain,setRetain]=useState(initial?.backupPolicy?.retain??3);const [error,setError]=useState("");
  const available=workers.data??[];
  return <form className="cb demo-form" onSubmit={event=>{
    event.preventDefault();setError("");
    if(step===0){if(name.trim().length<3){setError(t('Enter an experiment name.'));return;}setStep(1);return;}
    if(!cap.data||!selected.length||(cap.data.agentMode&&!coordinator)){setError(t('Select workers and a coordinator.'));return;}
    if(step===1){setStep(2);return;}
    void onSave({name,modelName:cap.data.modelId,modelArtifactId:"qwen-pinned",task,maxGenerations:generations,candidatesPerGeneration:candidates,alpha,sigma,decodeEngine:decoder,...(cap.data.agentMode?{coordinatorDeviceId:coordinator,backupPolicy:{interval,retain}}:{}),workerIds:selected,schedulerPolicy:"greedy",syncMode:"synchronous"}).catch((e:Error)=>setError(e.message));
  }}>
    <StepHeader steps={['Setup','Resources','Review']} current={step}/>
    {cap.isError&&<p className="note err" role="alert">{t('Runtime capabilities unavailable. Check the control service.')}</p>}
    {step===0&&<section className="setup-section"><h2>{t('Set up your experiment')}</h2><p className="hint">{t('Choose a workload and experiment size. Technical settings are optional.')}</p><div className="setup-grid">
      <label className="fg">{t('Experiment name')}<input autoFocus className="inp" required minLength={3} maxLength={160} value={name} onChange={e=>setName(e.target.value)}/></label>
      <label className="fg">{t('Workload')}<select className="sel" value={task} onChange={e=>{setTask(e.target.value);if(e.target.value==='arith16')setDecoder('hf_generate');}}>{cap.data?.workloads.map(value=><option key={value}>{value}</option>)}</select></label>
      <label className="fg">{t('Maximum generations')}<input className="inp" type="number" required min={1} max={1000} value={generations} onChange={e=>setGenerations(Number(e.target.value))}/></label>
      <label className="fg">{t('Candidates per generation')}<input className="inp" type="number" required min={2} max={256} value={candidates} onChange={e=>setCandidates(Number(e.target.value))}/></label>
    </div><p className="hint">{cap.data?.modelId} · {t('Pinned runtime model')}</p>
    <details className="advanced-panel"><summary>{t('Advanced settings')}</summary><div className="setup-grid">
      <label className="fg">{t("Alpha")}<input className="inp" type="number" required min={.0000001} max={1} step="any" value={alpha} onChange={e=>setAlpha(Number(e.target.value))}/></label>
      <label className="fg">{t("Sigma")}<input className="inp" type="number" required min={.0000001} max={1} step="any" value={sigma} onChange={e=>setSigma(Number(e.target.value))}/></label>
      <label className="fg">{t('Decoder')}<select className="sel" value={decoder} onChange={e=>setDecoder(e.target.value)}><option>{t("hf_generate")}</option>{task!=='arith16'&&<option>{t("hf_compact")}</option>}</select></label>
      <p className="hint">{t('FP32 evaluation · canonical CPU noise · exact worker restore.')}</p>
      <p className="hint">{t('Pinned revision:')} {cap.data?.modelRevision}</p>
    </div></details></section>}
    {step===1&&<section className="setup-section"><h2>{t('Choose your GPU resources')}</h2><p className="hint">{t('Jobs wait in the queue while selected devices are offline or contribution is OFF. Closing the browser does not cancel the job.')}</p>
      {cap.data?.agentMode&&<label className="fg">{t('Coordinator')}<select className="sel" required value={coordinator} onChange={e=>setCoordinator(e.target.value)}><option value="">{t('Select coordinator')}</option>{cap.data.coordinatorDevices?.map(d=><option key={d.deviceId} value={d.deviceId}>{d.workerId}</option>)}</select></label>}
      <fieldset className="worker-picker"><legend>{t('Configured workers')}</legend>{workers.isError&&<p role="alert">{t('Worker status unavailable')}</p>}{available.map(worker=><label className={selected.includes(worker.workerId)?'selected':''} key={worker.workerId}><input type="checkbox" disabled={!cap.data?.agentMode&&worker.contributionEnabled===false&&!selected.includes(worker.workerId)} checked={selected.includes(worker.workerId)} onChange={()=>setSelected(ids=>ids.includes(worker.workerId)?ids.filter(id=>id!==worker.workerId):[...ids,worker.workerId])}/><div><b>{worker.profile.gpuName}</b><small>{worker.workerId} · {t(worker.status)} · {t(worker.contributionEnabled===false?'OFF':'ON')}</small></div></label>)}{selected.filter(id=>!available.some(w=>w.workerId===id)).map(id=><label key={id}><input type="checkbox" checked onChange={()=>setSelected(ids=>ids.filter(value=>value!==id))}/>{id} · {t('No longer available')}</label>)}</fieldset>
    </section>}
    {step===2&&<section className="setup-section"><h2>{t('Review before saving')}</h2><dl className="setup-review"><div><dt>{t('Experiment name')}</dt><dd>{name}</dd></div><div><dt>{t('Workload')}</dt><dd>{task}</dd></div><div><dt>{t('Generations')}</dt><dd>{generations} × {candidates} {t("candidates")}</dd></div><div><dt>{t('Workers')}</dt><dd>{selected.join(', ')}</dd></div><div><dt>{t('Coordinator')}</dt><dd>{cap.data?.coordinatorDevices?.find(d=>d.deviceId===coordinator)?.workerId??t('Local coordinator')}</dd></div><div><dt>{t('Model')}</dt><dd>{cap.data?.modelId}</dd></div></dl>
      {cap.data?.agentMode&&<details className="advanced-panel"><summary>{t('Backup policy')}</summary><div className="setup-grid"><label className="fg">{t('Backup every K generations')}<input className="inp" type="number" required min={1} max={1000} value={interval} onChange={e=>setInterval(Number(e.target.value))}/></label><label className="fg">{t('Keep N recovery points')}<input className="inp" type="number" required min={1} max={1000} value={retain} onChange={e=>setRetain(Number(e.target.value))}/></label></div></details>}
      <p className="note">{t('Saving creates a draft. Submit it from the experiment page when ready.')}</p>
    </section>}
    {error&&<p className="note err" role="alert">{error}</p>}
    <footer className="setup-footer"><button type="button" className="btn" disabled={step===0||pending} onClick={()=>{setError('');setStep(step-1);}}>{t('Back')}</button><button className="btn pri" disabled={pending||!cap.data}>{t(step===2?'Save draft':'Continue')}</button></footer>
  </form>;
}

export function RuntimeControls({ experiment: e }: { experiment: Experiment }) {
  const {t}=useProduct();
  const { session, workspace } = useSession(); const navigate = useNavigate();
  const submit = useAccessMutation(submitExperiment); const cancel = useAccessMutation(requestExperimentCancel);
  const archive = useAccessMutation(archiveExperiment); const edit = useAccessMutation(updateExperiment);
  const [editing, setEditing] = useState(false);
  const policy=useAccessMutation((value:{interval:number;retain:number})=>apiPatch(`/api/v1/experiments/${e.experimentId}/backup-policy`,value));
  const [backupInterval,setBackupInterval]=useState(e.requestedBackupPolicy?.interval??e.backupPolicy?.interval??1);
  const [backupRetain,setBackupRetain]=useState(e.requestedBackupPolicy?.retain??e.backupPolicy?.retain??3);
  const permitted = e.ownerUserId === session?.user.userId || workspace?.role === "ADMIN";
  const terminal = ["COMPLETED", "CANCELLED", "FAILED", "DRAFT"].includes(e.status);
  const error = submit.error ?? cancel.error ?? archive.error ?? edit.error;
  const busy = submit.isPending || cancel.isPending || archive.isPending || edit.isPending;
  return <section className="card"><div className="ch"><h2>{t("Experiment management")}</h2></div><div className="cb demo-form">
    <p>{t("Selected workers:")}{e.workerIds?.join(", ")}</p>
    {e.waitingReason && <p className="note">{e.waitingReason}</p>}
    {e.cloudSync && <p>{t("Checkpoint sync:")}{e.cloudSync.status} {t("· Last synced generation:")}{e.cloudSync.lastCloudGeneration??'None'} {e.cloudSync.errorType}</p>}
    {e.monitoringPartial && <p>{t("Dashboard details show recent history. Full canonical history is retained in recovery points.")}</p>}
    {e.failureReason && <p className="note err" role="alert">{e.failureReason}</p>}
    {error && <p className="note err" role="alert">{error.message}</p>}
    {permitted && <div className="acts">
      {e.status === "DRAFT" && <><button className="btn" disabled={busy} onClick={() => setEditing(!editing)}>{t("Edit configuration")}</button><button className="btn pri" disabled={busy} onClick={() => void submit.mutateAsync(e.experimentId).catch(() => {})}>{t("Start experiment")}</button></>}
      {!terminal && !e.cancelRequested && <button className="btn dng" disabled={busy} onClick={() => void cancel.mutateAsync(e.experimentId).catch(() => {})}>{t("Cancel experiment")}</button>}
      <button className="btn" disabled title={t("Pause and resume require checkpoint lifecycle support beyond cancellation")}>{t("Pause / resume")}</button>
      <button className="btn" disabled title={t("Worker selection is immutable after submission")}>{t("Change workers during run")}</button>
      {terminal && <button className="btn dng" disabled={busy} onClick={() => { if (window.confirm("Archive this experiment and retain its evidence?")) void archive.mutateAsync(e.experimentId).then(() => navigate("/experiments")).catch(() => {}); }}>{t("Archive")}</button>}
    </div>}
    {e.cancelRequested && !terminal && <p className="note">{t("Stopping new leases; waiting for current candidates to restore and all selected workers to stop. The last completed checkpoint is retained.")}</p>}
    {permitted && e.coordinatorDeviceId && !['COMPLETED','CANCELLED','FAILED'].includes(e.status) && <form onSubmit={event=>{event.preventDefault();policy.mutate({interval:backupInterval,retain:backupRetain});}}><label className="fg">{t("Backup interval")}<input className="inp" type="number" required min={1} max={1000} value={backupInterval} onChange={event=>setBackupInterval(Number(event.target.value))}/></label><label className="fg">{t("Recovery points to retain")}<input className="inp" type="number" required min={1} max={1000} value={backupRetain} onChange={event=>setBackupRetain(Number(event.target.value))}/></label><button className="btn" disabled={policy.isPending}>{t("Apply backup policy at next generation")}</button>{policy.error && <p role="alert">{policy.error.message}</p>}</form>}
    {editing && e.status === "DRAFT" && <RuntimeConfiguration initial={e} pending={edit.isPending} onSave={async (configuration) => { await edit.mutateAsync({ experimentId: e.experimentId, configuration }); setEditing(false); }} />}
  </div></section>;
}

export function RuntimeResults({ experiment: e }: { experiment: Experiment }) {
  const {t}=useProduct();
  const generations = useGenerations(e.experimentId); const artifacts = useArtifacts();
  const [error, setError] = useState(""); const [downloading, setDownloading] = useState("");
  return <section className="card"><div className="ch"><h2>{t("Runtime results")}</h2><small>{t("Measured candidate rewards from the runtime ledger")}</small></div><div className="cb demo-form">
    <p>{t("Completed generations:")}{e.completedGenerations ?? 0}/{e.maxGenerations} {t("· Committed candidates in the current generation:")}{e.committedCandidateCount ?? 0}/{e.candidatesPerGeneration}</p>
    <RewardChart generations={generations.data ?? []} />
    <p className="hint">{t("Validation and test scores are unavailable: this run evaluates candidate rewards on the selected built-in workload.")}</p>
    {error && <p role="alert" className="note err">{error}</p>}
    {artifacts.data?.filter((a) => a.experimentId === e.experimentId).map((artifact) => <div className="demo-item" key={artifact.artifactId}><span>{artifact.name} · {artifact.sizeBytes?.toLocaleString()} {t("bytes")}</span><button className="btn" disabled={Boolean(downloading)} onClick={() => {
      setError(""); setDownloading(artifact.artifactId);
      void downloadArtifact(artifact.artifactId, artifact.name).catch((e: Error) => setError(e.message)).finally(() => setDownloading(""));
    }}>{t(downloading === artifact.artifactId ? "Downloading…" : "Download")}</button></div>)}
    <p className="hint">{t("A checkpoint download contains canonical raw FP16 weights. Load it with Track A's schema and verified hash; it is not a standalone Hugging Face model directory.")}</p>
  </div></section>;
}
