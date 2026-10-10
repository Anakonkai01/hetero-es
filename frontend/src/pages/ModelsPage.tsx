import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { registerModel } from "../api/access";
import { useAppState } from "../app/appState";
import { useSession } from "../app/session";
import { QueryState } from "../components/common/QueryState";
import { PageHeader } from "../components/ui/PageHeader";
import { useAccessMutation, useModels } from "../hooks/useAccess";

export function ModelsPage() { return IS_MOCK ? <MockModelsPage /> : <RuntimeModelsPage />; }

function MockModelsPage() {
  const query = useModels();
  const { session } = useSession();
  const { flash } = useAppState();
  const mutation = useAccessMutation(registerModel);
  const [name, setName] = useState("");
  const [source, setSource] = useState<"REFERENCE" | "UPLOAD_METADATA">("REFERENCE");
  const [reference, setReference] = useState("Qwen/Qwen2.5-0.5B-Instruct");
  const [revision, setRevision] = useState("main");
  const [files, setFiles] = useState<{ name: string; sizeBytes: number }[]>([]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await mutation.mutateAsync({ name, source, ...(source === "REFERENCE" ? { reference, revision } : { files }) });
      setName("");
      flash("Model metadata registered. No model files were uploaded.");
    } catch { /* The API error is displayed below. */ }
  }

  return <>
    <PageHeader title="Models" description="Model references in the selected workspace." />
    <div className="note">Register repository ID and revision. The Coordinator will resolve a fixed commit; each Worker downloads and caches that model directly. This local demo validates the reference structure only.</div>
    <section className="card"><div className="ch"><h2>Register model reference</h2></div><form className="cb demo-form" onSubmit={(event) => void submit(event)}>
      <label className="fg">Preset<select className="sel" onChange={(e) => { if (e.target.value) { setReference(e.target.value); setName(e.target.value.split("/")[1]); } }} defaultValue=""><option value="">Custom repository</option><option value="Qwen/Qwen2.5-0.5B-Instruct">Qwen2.5 0.5B Instruct</option><option value="HuggingFaceTB/SmolLM2-135M-Instruct">SmolLM2 135M Instruct</option></select></label>
      <label className="fg">Model name<input className="inp" value={name} onChange={(event) => setName(event.target.value)} required maxLength={160} /></label>
      <label className="fg">Source<select className="sel" value={source} onChange={(event) => setSource(event.target.value as typeof source)}><option value="REFERENCE">Repository reference</option></select></label>
      {source === "REFERENCE" ? <>
        <label className="fg">Repository ID<input className="inp" value={reference} onChange={(event) => setReference(event.target.value)} required placeholder="organization/model" /></label>
        <label className="fg">Revision<input className="inp" value={revision} onChange={(event) => setRevision(event.target.value)} required placeholder="Version or commit hash" /></label>
        <p className="hint">Repository revision · Reference validation only.</p>
      </> : <>
        <label className="fg">Model files<input type="file" multiple accept=".safetensors,.json,.model,.txt" onChange={(event) => setFiles(Array.from(event.target.files ?? []).map((file) => ({ name: file.name, sizeBytes: file.size })))} required /></label>
        <p className="hint">Select weights, config and tokenizer files. Only filenames and sizes will be registered; no file contents leave the browser.</p>
        {files.map((file) => <span className="mono" key={file.name}>{file.name} · {file.sizeBytes.toLocaleString()} bytes</span>)}
      </>}
      {mutation.isError && <div className="note err" role="alert">{mutation.error.message}</div>}
      <button className="btn pri" disabled={mutation.isPending}>{mutation.isPending ? "Registering…" : "Register reference"}</button>
    </form></section>
    <QueryState isPending={query.isPending} isError={query.isError} hasData={Boolean(query.data)} title="Could not load model metadata">
      <section className="card"><div className="ch"><h2>Registered model references</h2><Link className="link" to="/experiments/new">Create experiment →</Link></div><div className="cb demo-form">
        {!query.data?.length && <p className="hint">No models registered in this workspace.</p>}
        {query.data?.map((model) => <div className="demo-item" key={model.modelArtifactId}><div><b>{model.name}</b><div className="mono">{model.modelArtifactId}</div><div className="hint">{model.source === "REFERENCE" ? `${model.reference} @ ${model.revision}` : `${model.files?.length ?? 0} file metadata records`} · {model.ownerUserId === session?.user.userId ? "Owned" : model.ownerUserId}</div></div><span className="badge info">Metadata registered</span></div>)}
      </div></section>
    </QueryState>
  </>;
}
import { IS_MOCK } from "../lib/dataSource";
import { RuntimeModelsPage } from "./RuntimePages";
