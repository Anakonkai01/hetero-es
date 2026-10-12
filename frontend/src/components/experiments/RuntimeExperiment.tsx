import type {StudyDataset,StudyModel} from './StudyAssets';
import {useProduct,StepHeader} from '@heteroes/product-ui';
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router";
import { apiGet, apiPatch, apiPost, downloadArtifact } from "../../api/client";
import { archiveExperiment, requestExperimentCancel, submitExperiment, updateExperiment } from "../../api/experiments";
import { useSession, useScopeKey } from "../../app/session";
import { useAccessMutation } from "../../hooks/useAccess";
import { useWorkers } from "../../hooks/useWorkers";
import { useGenerations } from "../../hooks/useGenerations";
import { useArtifacts } from "../../hooks/useArtifacts";
import type { CreateExperimentRequest, Experiment } from "../../types/experiment";
import {useCandidates} from "../../hooks/useCandidates";
import {Badge} from "../ui/Badge";
import {CANDIDATE_STATUS} from "../../lib/labels";
import {formatBytes,shortId} from "../../lib/format";
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
  const [version,setVersion]=useState(initial?.recipeVersion??1);
  const [modelId,setModelId]=useState(initial?.modelArtifactId??'');const [datasetId,setDatasetId]=useState(initial?.datasetIds?.[0]??'');
  const [batchSize,setBatchSize]=useState(initial?.batchSize??32);const [batchSeed,setBatchSeed]=useState(initial?.batchSeed??11);
  const [schedule,setSchedule]=useState(initial?.sigmaSchedule??'constant');const [minimum,setMinimum]=useState(initial?.sigmaMinimum??.00025);
  const [maxTokens,setMaxTokens]=useState(initial?.maxNewTokens??512);
  const modelList=useQuery({queryKey:['study-models',...scope],queryFn:()=>apiGet<StudyModel[]>('/api/v1/models'),enabled:scope.every(Boolean)});
  const dataList=useQuery({queryKey:['study-datasets',...scope],queryFn:()=>apiGet<StudyDataset[]>('/api/v1/datasets'),enabled:scope.every(Boolean)});
  const customModel=modelList.data?.find(m=>m.modelArtifactId===modelId);
  const available=workers.data??[];
  return <form className="cb demo-form" onSubmit={event=>{
    event.preventDefault();setError("");
    if(step===0){if(name.trim().length<3){setError(t('Enter an experiment name.'));return;}setStep(1);return;}
    if(!cap.data||!selected.length||(cap.data.agentMode&&!coordinator)){setError(t('Select workers and a coordinator.'));return;}
    if(step===1){setStep(2);return;}
    if(version===2&&(!customModel?.manifest||!datasetId)){setError(t('Select a pinned model and frozen dataset.'));return;}
    void onSave({name,modelName:version===2?customModel!.reference:cap.data.modelId,modelArtifactId:version===2?modelId:"qwen-pinned",task:version===2?'text_math_v2':task,
      ...(version===2?{recipeVersion:2,datasetIds:[datasetId],batchSize,batchSeed,sigmaSchedule:schedule,sigmaMinimum:minimum,maxNewTokens:maxTokens,validationInterval:1}:{}),maxGenerations:generations,candidatesPerGeneration:candidates,alpha,sigma,decodeEngine:decoder,...(cap.data.agentMode?{coordinatorDeviceId:coordinator,backupPolicy:{interval,retain}}:{}),workerIds:selected,schedulerPolicy:"greedy",syncMode:"synchronous"}).catch((e:Error)=>setError(e.message));
  }}>
    <StepHeader steps={['Setup','Resources','Review']} current={step}/>
    {cap.isError&&<p className="note err" role="alert">{t('Runtime capabilities unavailable. Check the control service.')}</p>}
    {step===0&&<section className="setup-section"><h2>{t('Set up your experiment')}</h2><p className="hint">{t('Choose a workload and experiment size. Technical settings are optional.')}</p><div className="setup-grid">
      <label className="fg">{t('Experiment name')}<input autoFocus className="inp" required minLength={3} maxLength={160} value={name} onChange={e=>setName(e.target.value)}/></label>
      <label className="fg">{t('Experiment recipe')}<select className="sel" value={version} onChange={e=>{setVersion(Number(e.target.value));setDecoder('hf_generate');}}><option value={1}>{t('Built-in workload · Recipe v1')}</option>{cap.data?.agentMode&&<option value={2}>{t('Math dataset · Recipe v2')}</option>}</select></label>
      {version===1&&<label className="fg">{t('Workload')}<select className="sel" value={task} onChange={e=>{setTask(e.target.value);if(e.target.value==='arith16')setDecoder('hf_generate');}}>{cap.data?.workloads.map(value=><option key={value}>{value}</option>)}</select></label>}
      <label className="fg">{t('Maximum generations')}<input className="inp" type="number" required min={1} max={1000} value={generations} onChange={e=>setGenerations(Number(e.target.value))}/></label>
      <label className="fg">{t('Candidates per generation')}<input className="inp" type="number" required min={2} max={256} value={candidates} onChange={e=>setCandidates(Number(e.target.value))}/></label>
    </div>{version===2&&<div className="setup-grid">
      <label className="fg">{t('Pinned model')}<select className="sel" required value={modelId} onChange={e=>setModelId(e.target.value)}><option value="">{t('Select model')}</option>{modelList.data?.filter(m=>m.manifest&&['REGISTERED','READY'].includes(m.status)).map(m=><option key={m.modelArtifactId} value={m.modelArtifactId}>{m.name} · {m.revision}</option>)}</select></label>
      <label className="fg">{t('Frozen dataset')}<select className="sel" required value={datasetId} onChange={e=>setDatasetId(e.target.value)}><option value="">{t('Select dataset')}</option>{dataList.data?.map(d=><option key={d.datasetId} value={d.datasetId}>{d.name} · {d.counts.train}/{d.counts.validation}/{d.counts.test}</option>)}</select></label>
      <label className="fg">{t('Batch size')}<input className="inp" type="number" required min={1} max={1024} value={batchSize} onChange={e=>setBatchSize(Number(e.target.value))}/></label>
      <label className="fg">{t('Batch seed')}<input className="inp" type="number" required min={0} value={batchSeed} onChange={e=>setBatchSeed(Number(e.target.value))}/></label>
      <label className="fg">{t('Sigma schedule')}<select className="sel" value={schedule} onChange={e=>setSchedule(e.target.value)}><option value="constant">constant</option><option value="cosine">cosine</option></select></label>
      <label className="fg">{t('Minimum sigma')}<input className="inp" type="number" required min={1e-7} max={sigma} step="any" value={minimum} onChange={e=>setMinimum(Number(e.target.value))}/></label>
      <label className="fg">{t('Maximum output tokens')}<input className="inp" type="number" required min={1} max={2048} value={maxTokens} onChange={e=>setMaxTokens(Number(e.target.value))}/></label>
      <Link className="link" to="/models">{t('Import models and datasets')}</Link>
    </div>}<p className="hint">{cap.data?.modelId} · {t('Pinned runtime model')}</p>
    <details className="advanced-panel"><summary>{t('Advanced settings')}</summary><div className="setup-grid">
      <label className="fg">{t("Alpha")}<input className="inp" type="number" required min={.0000001} max={1} step="any" value={alpha} onChange={e=>setAlpha(Number(e.target.value))}/></label>
      <label className="fg">{t("Sigma")}<input className="inp" type="number" required min={.0000001} max={1} step="any" value={sigma} onChange={e=>setSigma(Number(e.target.value))}/></label>
      <label className="fg">{t('Decoder')}<select className="sel" value={decoder} onChange={e=>setDecoder(e.target.value)}><option>{t("hf_generate")}</option>{version===1&&task!=='arith16'&&<option>{t("hf_compact")}</option>}</select></label>
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
  const pause = useAccessMutation((id:string)=>apiPost(`/api/v1/experiments/${id}/pause`));
  const resume = useAccessMutation((id:string)=>apiPost(`/api/v1/experiments/${id}/resume`));
  const archive = useAccessMutation(archiveExperiment); const edit = useAccessMutation(updateExperiment);
  const [editing, setEditing] = useState(false);
  const policy=useAccessMutation((value:{interval:number;retain:number})=>apiPatch(`/api/v1/experiments/${e.experimentId}/backup-policy`,value));
  const [backupInterval,setBackupInterval]=useState(e.requestedBackupPolicy?.interval??e.backupPolicy?.interval??1);
  const [backupRetain,setBackupRetain]=useState(e.requestedBackupPolicy?.retain??e.backupPolicy?.retain??3);
  const permitted = e.ownerUserId === session?.user.userId || workspace?.role === "ADMIN";
  const terminal = ["COMPLETED", "CANCELLED", "FAILED", "DRAFT"].includes(e.status);
  const error = submit.error ?? cancel.error ?? archive.error ?? edit.error ?? pause.error ?? resume.error;
  const busy = submit.isPending || cancel.isPending || archive.isPending || edit.isPending || pause.isPending || resume.isPending;
  return <section className="card experiment-management"><div className="ch"><h2>{t("Experiment management")}</h2></div><div className="cb demo-form">
    <p>{t("Selected workers:")} {e.workerIds?.join(", ")}</p>
    {e.waitingReason && <p className="note">{e.waitingReason}</p>}

    {e.monitoringPartial && <p>{t("Dashboard details show recent history. Full canonical history is retained in recovery points.")}</p>}
    {e.failureReason && <p className="note err" role="alert">{e.failureReason}</p>}
    {error && <p className="note err" role="alert">{error.message}</p>}
    {permitted && <div className="acts">
      {e.status === "DRAFT" && <><button className="btn" disabled={busy} onClick={() => setEditing(!editing)}>{t("Edit configuration")}</button><button className="btn pri" disabled={busy} onClick={() => void submit.mutateAsync(e.experimentId).catch(() => {})}>{t("Start experiment")}</button></>}
      {!terminal && !e.cancelRequested && <button className="btn dng" disabled={busy} onClick={() => void cancel.mutateAsync(e.experimentId).catch(() => {})}>{t("Cancel experiment")}</button>}
      {e.coordinatorDeviceId && ['STARTING','RUNNING'].includes(e.status) && !e.cancelRequested && <button className="btn" disabled={busy} onClick={()=>void pause.mutateAsync(e.experimentId).catch(()=>{})}>{t('Pause after generation')}</button>}
      {e.coordinatorDeviceId && e.status==='PAUSED' && !e.cancelRequested && <button className="btn pri" disabled={busy} onClick={()=>void resume.mutateAsync(e.experimentId).catch(()=>{})}>{t('Resume experiment')}</button>}

      {terminal && <button className="btn dng" disabled={busy} onClick={() => { if (window.confirm("Archive this experiment and retain its evidence?")) void archive.mutateAsync(e.experimentId).then(() => navigate("/experiments")).catch(() => {}); }}>{t("Archive")}</button>}
    </div>}
    {e.cancelRequested && !terminal && <p className="note">{t("Stopping new leases; waiting for current candidates to restore and all selected workers to stop. The last completed checkpoint is retained.")}</p>}
    {e.status==='PAUSING' && !e.cancelRequested && <p className="note">{t('Finishing this generation, verifying its checkpoint and waiting for all selected processes to stop before releasing GPUs.')}</p>}
    {e.status==='PAUSED' && <p className="note">{t('Checkpoint verified and GPUs released. Resume queues the same experiment with its frozen configuration and new assignment credentials.')}</p>}
    {permitted && e.coordinatorDeviceId && !['COMPLETED','CANCELLED','FAILED'].includes(e.status) && <details className="advanced-panel"><summary>{t('Backup policy')}</summary><div><form onSubmit={event=>{event.preventDefault();policy.mutate({interval:backupInterval,retain:backupRetain});}}><label className="fg">{t("Backup interval")}<input className="inp" type="number" required min={1} max={1000} value={backupInterval} onChange={event=>setBackupInterval(Number(event.target.value))}/></label><label className="fg">{t("Recovery points to retain")}<input className="inp" type="number" required min={1} max={1000} value={backupRetain} onChange={event=>setBackupRetain(Number(event.target.value))}/></label><button className="btn" disabled={policy.isPending}>{t("Apply backup policy at next generation")}</button>{policy.error && <p role="alert">{policy.error.message}</p>}</form></div></details>}
    {editing && e.status === "DRAFT" && <RuntimeConfiguration initial={e} pending={edit.isPending} onSave={async (configuration) => { await edit.mutateAsync({ experimentId: e.experimentId, configuration }); setEditing(false); }} />}
  </div></section>;
}

export function RuntimeResults({experiment:e}:{experiment:Experiment}) {
 const {t}=useProduct();const generations=useGenerations(e.experimentId),artifacts=useArtifacts();
 const [selection,setSelection]=useState('');const [error,setError]=useState('');const [downloading,setDownloading]=useState('');
 const gs=generations.data??[];const selected=gs.find(g=>g.generationId===selection)??gs.find(g=>g.generationId===e.currentGenerationId)??gs.at(-1);
 const candidates=useCandidates(selected?.generationId);
 const mean=gs.filter(g=>g.rewardMean!==undefined).at(-1)?.rewardMean;
 const bests=gs.flatMap(g=>g.rewardBest===undefined?[]:[g.rewardBest]);
 return <section className="card"><div className="ch"><h2>{t('Experiment progress')}</h2><small>{t('Accepted runtime results')}</small></div><div className="cb">
 <dl className="detail-summary"><div><dt>{t('Completed generations')}</dt><dd>{e.completedGenerations??0} <small>/ {e.maxGenerations??'—'}</small></dd></div><div><dt>{t('Current accepted candidates')}</dt><dd>{selected?.committedCandidateCount??e.committedCandidateCount??0} <small>/ {selected?.candidateCount??e.candidatesPerGeneration}</small></dd></div><div><dt>{t('Latest mean reward')}</dt><dd>{mean?.toFixed(4)??'—'}</dd></div><div><dt>{t('Best candidate reward')}</dt><dd>{bests.length?Math.max(...bests).toFixed(4):'—'}</dd></div></dl>
 {generations.isError&&<p className="note err" role="alert">{t('Generation history unavailable')}</p>}<div className="chart-wrap"><div className="section-title"><h2>{t('Reward by generation')}</h2><span className="hint">{e.task}</span></div><RewardChart generations={gs}/></div><p className="info-caption">{e.recipeVersion===2?`${t('Best validation accuracy')}: ${e.validationScore??'—'} · ${t('Test accuracy')}: ${e.studyMetrics?.testLocked?t('Locked'):e.testScore??'—'} · ${t('Export reload')}: ${e.studyMetrics?.independentReloadPassed?t('Verified'):t('Pending')}`:t('Validation and test scores are unavailable: this run evaluates candidate rewards on the selected built-in workload.')}</p>
 <section className="experiment-inspector"><div className="generation-picker"><div><h3>{t('Generation & candidate inspector')}</h3><p>{t('Inspect seeds, allocation and accepted rewards for each generation.')}</p></div><label className="fg"><span className="sr-only">{t('Select generation')}</span><select className="sel" value={selected?.generationId??''} onChange={event=>setSelection(event.target.value)} disabled={!gs.length}>{!gs.length&&<option value="">{t('No generations yet')}</option>}{gs.map((g,i)=><option key={g.generationId} value={g.generationId}>{t('Generation')} {i} · {t(g.status)}</option>)}</select></label></div>
 {selected&&<p className="info-caption"><Link to={`/experiments/${e.experimentId}/generations/${selected.generationId}`}>{t('Open generation')} →</Link> · <span className="mono">{selected.generationId}</span></p>}
 {candidates.isError?<p className="note err" role="alert">{t('Candidate history unavailable')}</p>:candidates.isPending&&selected?<p role="status">{t('Loading candidates…')}</p>:candidates.data?.length?<div className="scroll"><table className="inspector-table"><thead><tr>{['Candidate','Seed','Status','Assigned worker','Reward'].map(label=><th key={label} scope="col">{t(label)}</th>)}</tr></thead><tbody>{candidates.data.map(c=><tr key={c.candidateId}><td><Link className="mono" to={`/experiments/${e.experimentId}/generations/${c.generationId}/candidates/${c.candidateId}`}>{shortId(c.candidateId)}</Link></td><td className="seed">{c.seed}</td><td><Badge info={CANDIDATE_STATUS[c.status]}/></td><td>{c.workerId?<Link className="mono" to={`/workers/${c.workerId}`}>{c.workerId}</Link>:t('Not assigned')}</td><td className="seed">{c.reward?.toFixed(4)??'—'}</td></tr>)}</tbody></table></div>:<p className="note">{t('Candidates appear after the coordinator opens a generation.')}</p>}
 <p className="info-caption">{t('Candidate seeds are derived from the experiment, generation and candidate index. Retries reuse the same seed.')}</p></section><div className="recovery-strip"><span>{t('Checkpoint sync')}: <b>{t(e.cloudSync?.status??'Not reported')}</b></span><small>{t('Last synced generation')}: {e.cloudSync?.lastCloudGeneration??'—'}</small><Link className="link" to={`/artifacts?experiment=${e.experimentId}`}>{t('View artifacts')} →</Link></div>
 {error&&<p role="alert" className="note err">{error}</p>}{artifacts.isError&&<p className="note err" role="alert">{t('Artifact list unavailable')}</p>}
 {artifacts.data?.filter(a=>a.experimentId===e.experimentId).map(a=><div className="demo-item" key={a.artifactId}><span>{a.name}<small className="hint"> · {formatBytes(a.sizeBytes)} · {t(a.status)}</small></span><button className="btn" disabled={!!downloading||a.status!=='READY'} onClick={()=>{setError('');setDownloading(a.artifactId);void downloadArtifact(a.artifactId,a.name).catch((err:Error)=>setError(err.message)).finally(()=>setDownloading(''));}}>{t(downloading===a.artifactId?'Downloading…':'Download')}</button></div>)}<p className="info-caption">{t("A checkpoint download contains canonical raw FP16 weights. Load it with Track A's schema and verified hash; it is not a standalone Hugging Face model directory.")}</p>
 </div></section>;
}
