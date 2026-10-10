import type { Experiment } from "../../types/experiment";

export function ExperimentResults(props: { experiment: Experiment }) { return IS_MOCK ? <MockExperimentResults {...props} /> : <RuntimeResults {...props} />; }

function MockExperimentResults({ experiment: e }: { experiment: Experiment }) {
  if (!e.maxGenerations) return null;
  const completed = e.completedGenerations ?? 0;
  const points = Array.from({ length: completed + 1 }, (_, i) => ({ x: 30 + i / Math.max(1, e.maxGenerations!) * 540, y: 160 - Math.min(0.9, 0.4 + i * 0.025) * 140 }));
  function exportState() {
    const url = URL.createObjectURL(new Blob([JSON.stringify({ simulated: true, experimentId: e.experimentId, modelReference: e.modelArtifactId, modelVersion: e.modelVersion, completedGenerations: completed, validationScore: e.validationScore, testScore: e.testScore, checkpointSavedAt: e.checkpointSavedAt, note: "Demo run state only; contains no model weights." }, null, 2)], { type: "application/json" }));
    const a = document.createElement("a"); a.href = url; a.download = `${e.experimentId}-demo-state.json`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <section className="card"><div className="ch"><h2>Training dashboard</h2><small>Simulated figures — no model is evaluated</small></div><div className="cb demo-form">
    <div className="acts"><span>Generations: <b>{completed}/{e.maxGenerations}</b></span><span>Current candidates: <b>{e.mockCandidateProgress ?? 0}/{e.candidatesPerGeneration}</b></span><span>Workers: <b>{e.workerIds?.length ?? 0}</b></span></div>
    <figure><figcaption>Validation score by completed generation (mock)</figcaption><svg viewBox="0 0 600 190" role="img" aria-label="Simulated validation score curve"><path d="M30 10V160H580" fill="none" stroke="currentColor" /><polyline points={points.map((p) => `${p.x},${p.y}`).join(" ")} fill="none" stroke="#16a085" strokeWidth="3" />{points.map((p, i) => <circle key={i} cx={p.x} cy={p.y} r="4" fill="#16a085"><title>Generation {i}: {(0.4 + i * 0.025).toFixed(3)} (mock)</title></circle>)}<text x="30" y="185" fill="currentColor">0</text><text x="520" y="185" fill="currentColor">Generation {e.maxGenerations}</text></svg></figure>
    <table className="demo-table"><thead><tr><th>Evaluation split</th><th>Score (mock)</th><th>When evaluated</th></tr></thead><tbody><tr><td>Validation</td><td>{e.validationScore?.toFixed(3) ?? "Pending"}</td><td>After each completed generation</td></tr><tr><td>Test</td><td>{e.testScore?.toFixed(3) ?? "Pending"}</td><td>Only after training completes</td></tr></tbody></table>
    {e.checkpointSavedAt && <><span>Saved model state: {e.modelVersion} · {e.checkpointSavedAt}</span><button className="btn" onClick={exportState}>Download demo run state (JSON)</button><span className="hint">Real Coordinator integration must supply a checkpoint download, such as safetensors and model configuration. This JSON contains no weights.</span></>}
  </div></section>;
}
import { IS_MOCK } from "../../lib/dataSource";
import { RuntimeResults } from "./RuntimeExperiment";
