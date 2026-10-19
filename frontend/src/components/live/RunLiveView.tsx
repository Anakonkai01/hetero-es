import { useProduct } from "@heteroes/product-ui";
import { useReducedMotion } from "../../hooks/useReducedMotion";
import { useRunPlayer } from "../../hooks/useRunPlayer";
import type { TimelineSource } from "../../hooks/useRunTimeline";
import { formatDuration } from "../../lib/diagramLayout";
import { describeEvent,fillTemplate } from "../../lib/eventText";
import type { Timeline } from "../../lib/runFrame";
import { LiveDiagram } from "./LiveDiagram";
import { PlayerBar } from "./PlayerBar";
import { RunGantt } from "./RunGantt";
import "./live.css";

const PHASES = ["Evaluate candidates in parallel", "Update and publish the model"] as const;

function Ribbon({ phase, progress, committed, count }: { phase?: string; progress: number; committed: number | null; count: number | null }) {
  const { t } = useProduct();
  const step = phase === "evaluating" ? 0 : phase === "updating" ? 1 : phase === "between" || phase === "finished" ? 2 : -1;
  return (
    <ol className="lv-ribbon" aria-label={t("Phases of a generation")}>
      {PHASES.map((label, index) => (
        <li key={label} className={index < step ? "done" : index === step ? "now" : ""} aria-current={index === step ? "step" : undefined}>
          <span className="lv-step-no">{index < step ? "✓" : index + 1}</span>
          <span>{t(label)}{index === 0 && step === 0 && count ? ` · ${committed ?? 0}/${count}` : ""}</span>
          {index === step && <span className="lv-step-bar"><span style={{ width: `${Math.round(Math.min(1, Math.max(0, progress)) * 100)}%` }} /></span>}
        </li>
      ))}
      <li className={step === 2 ? (phase === "finished" ? "done" : "now") : ""}>
        <span className="lv-step-no">{phase === "finished" ? "✓" : 3}</span><span>{t(phase === "finished" ? "Experiment finished" : "Next generation")}</span>
      </li>
    </ol>
  );
}

/** The whole "see the coordinator hand out work and the GPUs do it" screen, for a running run and for a replay. */
export type LiveVariant = "full" | "compact" | "hero";

/** full: everything; compact: controls, numbers and diagram (dashboard); hero: only the looping diagram (home page). */
export function RunLiveView({ timeline, mode, source, clockOffsetMs = 0, title, variant = "full", afterLive = false }: { timeline: Timeline; mode: "live" | "replay"; source?: TimelineSource; clockOffsetMs?: number; title?: string; variant?: LiveVariant; afterLive?: boolean }) {
  const { t } = useProduct();
  const reduced = useReducedMotion();
  const player = useRunPlayer(timeline, mode, clockOffsetMs, reduced, variant === "hero" ? { loop: true, speed: 4 } : variant === "compact" && mode === "replay" ? { loop: true, speed: 8 } : { afterLive });
  const { frame, bounds } = player;
  if (!frame || !bounds) return null;
  const generation = frame.generation;
  const latestReward = frame.rewards.at(-1);
  const active = frame.workers.filter(w => w.state === "busy").length;

  return (
    <section className={`lv lv-${variant}`} aria-label={title ?? t("Live view of the run")}>
      {variant !== "hero" && <PlayerBar player={player} mode={mode} source={source} />}

      <div className="lv-stats">
        <div><span className="hint">{t("Generation")}</span><b>{generation ? `${generation.index + 1}/${generation.total ?? "?"}` : "–"}</b></div>
        <div><span className="hint">{t("Candidates committed")}</span><b>{frame.totals.committed}/{frame.totals.total ?? "?"}</b></div>
        {variant !== "hero" && <div><span className="hint">{t("GPUs working")}</span><b>{active}/{frame.workers.filter(w => w.state !== "unstarted").length}</b></div>}
        {variant !== "hero" && <div><span className="hint">{t("Latest mean reward")}</span><b>{latestReward ? latestReward.mean.toFixed(4) : "–"}</b></div>}
        <div><span className="hint">{t("Elapsed")}</span><b>{formatDuration(frame.atMs - bounds.startMs)}</b></div>
      </div>

      {variant === "full" && <Ribbon phase={generation?.phase} progress={generation?.phaseProgress ?? 0} committed={generation?.committed ?? null} count={generation?.count ?? null} />}

      <div className="lv-stage">
        <LiveDiagram frame={frame} reducedMotion={reduced} narrow={variant === "hero"} />
        <ul className="lv-notices" aria-live="polite">
          {frame.marks.slice(-3).map(mark => {
            const d = describeEvent(mark.type, { worker_id: mark.workerId ?? undefined, error: mark.detail, generation: mark.generation ?? undefined }, mark.workerId ?? undefined);
            return <li key={`${mark.type}-${mark.atMs}`} className={`lv-notice lv-notice-${d.tone}`}>{fillTemplate(t(d.template), d.params)}</li>;
          })}
        </ul>
      </div>

      {variant === "full" && <>
      <h3 className="lv-h">{t("Timeline")}</h3>
      <RunGantt timeline={timeline} frame={frame} bounds={bounds} onSeek={player.seek} />
      <div className="lv-legend" aria-hidden="true">
        <span><i className="lv-sw lv-job-succeeded" /> {t("Committed")}</span>
        <span><i className="lv-sw lv-job-running" /> {t("Running")}</span>
        <span><i className="lv-sw lv-job-failed" /> {t("Failed attempt")}</span>
        <span><i className="lv-sw lv-update" /> {t("Update and publish the model")}</span>
      </div>

      <div className="scroll">
        <table className="lv-table">
          <caption className="sr-only">{t("GPUs in this run")}</caption>
          <thead><tr><th scope="col">{t("GPU")}</th><th scope="col">{t("Now")}</th><th scope="col">{t("Done")}</th><th scope="col">{t("Failed")}</th><th scope="col">{t("Seconds per candidate")}</th><th scope="col">{t("Last reward")}</th></tr></thead>
          <tbody>
            {frame.workers.map(worker => (
              <tr key={worker.id}>
                <th scope="row">{worker.id}</th>
                <td>{t(worker.state === "busy" ? "Working" : worker.state === "offline" ? "Connection lost" : worker.state === "unstarted" ? "Not started" : worker.state === "starting" ? "Loading the model" : "Waiting for work")}</td>
                <td>{worker.done}</td><td>{worker.failed}</td>
                <td>{worker.meanSeconds !== null ? worker.meanSeconds.toFixed(1) : "–"}</td>
                <td>{worker.lastReward !== null ? worker.lastReward.toFixed(2) : "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      </>}
    </section>
  );
}
