import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { PreferencesControl, ProductMark, useProduct } from "@heteroes/product-ui";
import { Term } from "../components/ui/Term";
import { useDemoTimeline } from "../hooks/useDemoTimeline";
import { fillTemplate } from "../lib/eventText";
import { explainFromTimeline, noiseCloud, type Explanation } from "../lib/esExplain";
import { useSession } from "../app/session";

const WORKER_COLORS = ["var(--acc)", "var(--chart-secondary)", "#c2410c", "#7c3aed"];
const STEPS = 5;

function Picture({ step, e }: { step: number; e: Explanation }) {
  const { t } = useProduct();
  const cloud = useMemo(() => noiseCloud(Math.max(e.candidates.length, 12), 11, 120), [e.candidates.length]);
  const workers = [...new Set(e.candidates.map(c => c.worker))];
  const colorOf = (worker: string) => WORKER_COLORS[workers.indexOf(worker) % WORKER_COLORS.length];
  const maxReward = Math.max(0.01, ...e.candidates.map(c => c.reward));
  const maxWeight = Math.max(0.01, ...e.weights.map(Math.abs));
  const pull = cloud.slice(0, e.weights.length).reduce((sum, p, i) => ({ x: sum.x + p.x * e.weights[i], y: sum.y + p.y * e.weights[i] }), { x: 0, y: 0 });
  const length = Math.hypot(pull.x, pull.y) || 1;
  const arrow = { x: (pull.x / length) * Math.min(70, length / 2.2), y: (pull.y / length) * Math.min(70, length / 2.2) };

  if (step <= 2 || step === 3) {
    return (
      <svg viewBox="-160 -150 320 300" className="explain-svg" role="img" aria-label={t("Picture of the current model and its random variations")}>
        <circle r="120" fill="none" stroke="var(--line)" strokeDasharray="4 6" />
        {step >= 1 && cloud.map((p, i) => {
          const weight = e.weights[i] ?? 0;
          const colour = step >= 3 ? (weight >= 0 ? "var(--success)" : "var(--danger)") : e.candidates[i] ? colorOf(e.candidates[i].worker) : "var(--mut)";
          const radius = step >= 3 ? 4 + Math.min(1, Math.abs(weight) / maxWeight) * 7 : step === 2 ? 4 + ((e.candidates[i]?.reward ?? 0) / maxReward) * 7 : 5;
          return <g key={i}><line x1="0" y1="0" x2={p.x} y2={p.y} stroke="var(--line)" /><circle cx={p.x} cy={p.y} r={radius} fill={colour} opacity={step >= 3 && weight < 0 ? 0.55 : 0.9} /></g>;
        })}
        {step >= 3 && <line x1="0" y1="0" x2={arrow.x} y2={arrow.y} stroke="var(--ink)" strokeWidth="3" markerEnd="url(#explain-arrow)" />}
        <defs><marker id="explain-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="var(--ink)" /></marker></defs>
        <circle r="11" fill="var(--ink)" /><text y="30" textAnchor="middle" fontSize="13" fill="var(--ink)">{step >= 3 ? t("model, moving") : t("the model")}</text>
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 360 260" className="explain-svg" role="img" aria-label={t("Reward of the model after each generation")}>
      {[0, 1, 2, 3].map(i => <line key={i} x1="40" x2="350" y1={20 + i * 60} y2={20 + i * 60} stroke="var(--line2)" />)}
      {e.generations.map((g, i) => {
        const x = 70 + i * (e.generations.length > 1 ? 250 / (e.generations.length - 1) : 0);
        const top = Math.max(0.4, ...e.generations.map(h => h.best));
        const y = (v: number) => 200 - (v / top) * 170;
        return <g key={g.index}>{i > 0 && <><line x1={70 + (i - 1) * 250 / (e.generations.length - 1)} y1={y(e.generations[i - 1].mean)} x2={x} y2={y(g.mean)} stroke="var(--acc)" strokeWidth="3" /></>}<circle cx={x} cy={y(g.mean)} r="6" fill="var(--acc)"><title>{`${t("Generation")} ${g.index + 1}: ${g.mean.toFixed(3)}`}</title></circle><circle cx={x} cy={y(g.best)} r="4" fill="var(--chart-secondary)" /><text x={x} y="228" textAnchor="middle" fontSize="12" fill="var(--mut)">{g.index + 1}</text></g>;
      })}
      <text x="195" y="252" textAnchor="middle" fontSize="12" fill="var(--mut)">{t("Generation")}</text>
      <text x="44" y="14" fontSize="12" fill="var(--mut)">{t("reward")}</text>
    </svg>
  );
}

/** "How it works": five short steps with the numbers of a real run of this lab. */
export function ExplainPage() {
  const { t } = useProduct();
  const { session } = useSession();
  const demo = useDemoTimeline();
  const e = useMemo(() => (demo.data ? explainFromTimeline(demo.data) : undefined), [demo.data]);
  const [step, setStep] = useState(0);
  useEffect(() => {
    const key = (event: KeyboardEvent) => { if (event.key === "ArrowRight") setStep(s => Math.min(STEPS - 1, s + 1)); if (event.key === "ArrowLeft") setStep(s => Math.max(0, s - 1)); };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, []);
  const gpus = e ? new Set(e.candidates.map(c => c.worker)).size : 0;
  const best = e?.candidates.length ? Math.max(...e.candidates.map(c => c.reward)) : 0;
  const text = [
    { title: t("Start from the model you have"), body: <>{t("Evolution Strategies improves a model without computing gradients. It starts from the current model, called θ.")}</> },
    { title: t("Nudge it at random, many times"), body: <>{e ? fillTemplate(t("Each nudge is a new candidate: the model plus a random change. A seed number makes the change reproducible on any computer. This run made {n} candidates per generation."), { n: e.candidates.length }) : t("Each nudge is a new candidate: the model plus a random change.")} <Term term="candidate" /> · <Term term="seed" /></> },
    { title: t("Test every nudge on a GPU"), body: <>{e ? fillTemplate(t("Every candidate is scored independently, so {gpus} different GPUs shared the work. The best score in the first generation was {best}."), { gpus, best: best.toFixed(3) }) : ""} <Term term="reward" /> · <Term term="lease" /></> },
    { title: t("Move towards what worked"), body: <>{t("Scores are turned into weights: better than average pulls the model towards that nudge, worse pushes it away. The model takes one small step along the weighted average.")} <Term term="generation" /></> },
    { title: t("Repeat, and keep the progress"), body: <>{e ? fillTemplate(t("After each generation the new model is saved. This run did {generations} generations and {total} candidate evaluations in total."), { generations: e.generations.length, total: e.totalCandidates }) : ""} <Term term="checkpoint" /> · <Term term="replay" /></> },
  ];
  return (
    <div className="public-site explain">
      <header className="public-header"><Link className="public-brand" to="/"><ProductMark />Hetero<span>ES</span></Link><div className="acts"><PreferencesControl /><Link className="btn pri" to={session ? "/dashboard" : "/login"}>{t(session ? "Open dashboard" : "Sign in")}</Link></div></header>
      <main id="main-content" className="explain-main">
        <p className="eyebrow">{t("How it works")}</p>
        <h1>{t("Training a model by trial and selection")}</h1>
        <p className="explain-intro">{t("The numbers below come from a real run in this lab, not from a simulation.")}</p>
        <div className="explain-stage">
          <div className="explain-text" aria-live="polite">
            <span className="explain-count">{step + 1} / {STEPS}</span>
            <h2>{text[step].title}</h2>
            <p>{text[step].body}</p>
          </div>
          <div className="explain-art">{e && e.candidates.length ? <Picture step={step} e={e} /> : <p className="hint" role="status">{demo.isPending ? t("Loading…") : t("The example run is not available on this server.")}</p>}
            {e && step === 2 && <ul className="explain-bars" aria-label={t("Reward of each candidate")}>{e.candidates.map((c, i) => <li key={i}><span className="mono">{c.name}</span><span className="explain-bar"><i style={{ width: `${Math.max(2, (c.reward / Math.max(0.01, ...e.candidates.map(x => x.reward))) * 100)}%`, background: WORKER_COLORS[[...new Set(e.candidates.map(x => x.worker))].indexOf(c.worker) % WORKER_COLORS.length] }} /></span><span className="mono">{c.reward.toFixed(2)}</span><small>{c.worker}</small></li>)}</ul>}
          </div>
        </div>
        <nav className="explain-nav" aria-label={t("Steps")}>
          <button type="button" className="btn" disabled={step === 0} onClick={() => setStep(step - 1)}>← {t("Back")}</button>
          <span className="explain-dots">{Array.from({ length: STEPS }, (_, i) => <button key={i} type="button" className={i === step ? "dot on" : "dot"} aria-label={`${t("Step")} ${i + 1}`} aria-current={i === step ? "step" : undefined} onClick={() => setStep(i)} />)}</span>
          {step < STEPS - 1 ? <button type="button" className="btn pri" onClick={() => setStep(step + 1)}>{t("Next")} →</button> : <Link className="btn pri" to="/">{t("See it live")} →</Link>}
        </nav>
      </main>
    </div>
  );
}
