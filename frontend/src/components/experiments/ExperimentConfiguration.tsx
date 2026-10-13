import {useProduct} from '@heteroes/product-ui';
import { useState, useRef, useEffect } from "react";
import { Link } from "react-router";
import { uploadDataset } from "../../api/access";
import { useSession } from "../../app/session";
import { useAccessMutation, useDatasets, useModels, useResources } from "../../hooks/useAccess";
import { useWorkers } from "../../hooks/useWorkers";
import { TASK_FIELDS, type DatasetSplit, type DatasetTask } from "../../types/dataset";
import type { CreateExperimentRequest, Experiment } from "../../types/experiment";

const splits: DatasetSplit[] = ["train", "validation", "test"];
export function ExperimentConfiguration(props: Parameters<typeof MockExperimentConfiguration>[0]) { return IS_MOCK ? <MockExperimentConfiguration {...props} /> : <RuntimeConfiguration {...props} />; }

function MockExperimentConfiguration({ initial, onSave, pending }: { initial?: Experiment; onSave: (config: CreateExperimentRequest) => Promise<unknown>; pending: boolean }) {
  const {t}=useProduct();
  const { session, workspace } = useSession();
  const models = useModels(); const resources = useResources(); const workers = useWorkers(); const datasets = useDatasets();
  const upload = useAccessMutation(uploadDataset);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const [name, setName] = useState(initial?.name ?? "");
  const [modelId, setModelId] = useState(initial?.modelArtifactId ?? "");
  const [task, setTask] = useState<DatasetTask>(initial?.task && Object.hasOwn(TASK_FIELDS, initial.task) ? initial.task as DatasetTask : "sentiment");
  const [generations, setGenerations] = useState(initial?.maxGenerations ?? 5);
  const [candidates, setCandidates] = useState(initial?.candidatesPerGeneration ?? 8);
  const [workerIds, setWorkers] = useState<string[]>(initial?.workerIds ?? []);
  const [datasetIds, setDatasets] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [reading, setReading] = useState(false);
  const grants = resources.data?.grants.filter((g) => g.userId === session?.user.userId && g.status === "ACTIVE").flatMap((g) => g.workerIds) ?? [];
  const choices = workers.data?.filter((w) => grants.includes(w.workerId) && !resources.data?.pools.some((p) => p.drainingWorkerIds.includes(w.workerId))) ?? [];
  const model = models.data?.find((m) => m.modelArtifactId === modelId) ?? models.data?.[0];
  const selected = splits.map((split) => {
    const list = datasets.data?.filter((d) => d.task === task && d.split === split) ?? [];
    return list.find((d) => d.datasetId === datasetIds[split]) ?? list.find((d) => initial?.datasetIds?.includes(d.datasetId)) ?? list[0];
  });
  return <form className="cb demo-form" onSubmit={(e) => {
    e.preventDefault(); setError("");
    if (!model || !workspace || selected.some((d) => !d) || !workerIds.length) { setError("Select a model, Workers and all three dataset splits."); return; }
    void onSave({ name, modelName: model.name, modelArtifactId: model.modelArtifactId, task, maxGenerations: generations, candidatesPerGeneration: candidates, datasetIds: selected.map((d) => d!.datasetId), workerIds, schedulerPolicy: initial?.schedulerPolicy ?? "capacity-weighted", syncMode: "synchronous" }).catch((e: Error) => setError(e.message));
  }}>
    <p>{t("Workspace:")}<b>{workspace?.name ?? "Select or create a workspace first"}</b></p>
    <label className="fg">{t("Experiment name")}<input className="inp" required minLength={3} maxLength={160} value={name} onChange={(e) => setName(e.target.value)} /></label>
    <label className="fg">{t("Model")}<select className="sel" value={model?.modelArtifactId ?? ""} onChange={(e) => setModelId(e.target.value)} required><option value="" disabled>{t("Select a model")}</option>{models.data?.map((m) => <option key={m.modelArtifactId} value={m.modelArtifactId}>{m.name} · {m.reference}@{m.revision}</option>)}</select></label>
    <Link className="link" to="/models">{t("Register a Hugging Face reference")}</Link>
    <label className="fg">{t("Task")}<select className="sel" value={task} onChange={(e) => { setTask(e.target.value as DatasetTask); setDatasets({}); }}><option value="sentiment">{t("Sentiment classification")}</option><option value="qa">{t("Question answering")}</option><option value="summarization">{t("Summarization")}</option></select></label>
    <p className="hint">{t("Required fields:")}{" "}{TASK_FIELDS[task].join(", ")} {t("(strings). JSON: array of objects; JSONL: one object per line; CSV: header and records. Structural checks only. Local limit: 5 MiB/file.")}</p>
    {splits.map((split, i) => <fieldset key={split} disabled={reading || upload.isPending}><legend>{split}</legend>
      <label className="fg">{t("Upload")}{split}<input type="file" accept=".json,.jsonl,.csv" onChange={(e) => {
        const file = e.target.files?.[0]; if (!file) return;
        setError(""); if (file.size > 5 * 1024 * 1024) { setError("File exceeds 5 MiB."); return; }
        const currentTask = task; setReading(true);
        void file.arrayBuffer().then((buffer) => new TextDecoder("utf-8", { fatal: true }).decode(buffer)).then((content) => { if (!mounted.current) throw new Error("Upload stopped because the active user or workspace changed."); return upload.mutateAsync({ name: file.name, content, task: currentTask, split }); }).then((d) => setDatasets((current) => ({ ...current, [split]: d.datasetId }))).catch((e: Error) => setError(e.message)).finally(() => setReading(false));
      }} /></label>
      <label className="fg">{t("Registered dataset")}<select className="sel" value={selected[i]?.datasetId ?? ""} onChange={(e) => setDatasets((current) => ({ ...current, [split]: e.target.value }))}><option value="" disabled>{t("Select dataset")}</option>{datasets.data?.filter((d) => d.task === task && d.split === split).map((d) => <option key={d.datasetId} value={d.datasetId}>{d.name}</option>)}</select></label>
      {selected[i] && <><p>{selected[i]!.sizeBytes.toLocaleString()} {t("bytes ·")}{selected[i]!.recordCount} {t("records ·")}{selected[i]!.fields.length} {t("fields:")}{" "}{selected[i]!.fields.join(", ")}</p>
        <details><summary>{t("Preview (up to 10 records)")}</summary><div className="dataset-preview"><table className="demo-table"><thead><tr>{selected[i]!.fields.map((f) => <th key={f}>{f}</th>)}</tr></thead><tbody>{selected[i]!.preview.map((row, j) => <tr key={j}>{selected[i]!.fields.map((f) => <td key={f}>{row[f]}</td>)}</tr>)}</tbody></table></div></details></>}
    </fieldset>)}
    <label className="fg">{t("Maximum generations")}<input className="inp" type="number" min={1} max={1000} required value={generations} onChange={(e) => setGenerations(Number(e.target.value))} /></label>
    <label className="fg">{t("Candidates per generation")}<input className="inp" type="number" min={1} max={256} required value={candidates} onChange={(e) => setCandidates(Number(e.target.value))} /></label>
    <fieldset><legend>{t("Allocated Workers")}</legend>{choices.map((w) => <label className="demo-check" key={w.workerId}><input type="checkbox" checked={workerIds.includes(w.workerId)} onChange={() => setWorkers((ids) => ids.includes(w.workerId) ? ids.filter((id) => id !== w.workerId) : [...ids, w.workerId])} />{w.profile.gpuName} · {w.workerId}</label>)}{!choices.length && <Link className="link" to="/workspace/current">{t("Workspace resources")}</Link>}</fieldset>
    {error && <div className="note err" role="alert">{error}</div>}
    <button className="btn pri" disabled={pending || reading || upload.isPending || !workspace}>{t("Save draft")}</button>
  </form>;
}
import { IS_MOCK } from "../../lib/dataSource";
import { RuntimeConfiguration } from "./RuntimeExperiment";
