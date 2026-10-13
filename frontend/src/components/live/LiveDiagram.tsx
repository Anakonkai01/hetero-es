import { useMemo } from "react";
import { useProduct } from "@heteroes/product-ui";
import { candidateLabel, connector, layoutWorkers, packetPosition } from "../../lib/diagramLayout";
import { fillTemplate } from "../../lib/eventText";
import type { Frame, WorkerFrame } from "../../lib/runFrame";

const RING_R = 24;
const CIRC = 2 * Math.PI * RING_R;

function stateText(worker: WorkerFrame, t: (key: string) => string): string {
  if (worker.state === "busy" && worker.job) return fillTemplate(t("Evaluating {candidate}"), { candidate: candidateLabel(worker.job.candidateId) });
  if (worker.state === "offline") return t("Connection lost");
  if (worker.state === "unstarted") return t("Not started");
  if (worker.state === "starting") return t("Loading the model");
  return t("Waiting for work");
}

/** Coordinator in the middle of the top, one card per GPU below it, and packets flying along the connectors. */
export function LiveDiagram({ frame, reducedMotion }: { frame: Frame; reducedMotion: boolean }) {
  const { t } = useProduct();
  const layout = useMemo(() => layoutWorkers(frame.workers.length), [frame.workers.length]);
  const { coordinator } = layout;
  const anchor = { x: coordinator.cx, y: coordinator.y + coordinator.h };
  const generation = frame.generation;
  const busy = frame.workers.filter(w => w.state === "busy").length;

  return (
    <svg className="lv-diagram" viewBox={`0 0 ${layout.width} ${layout.height}`} role="img"
      aria-label={fillTemplate(t("Diagram: the coordinator and {count} GPUs, {busy} working"), { count: frame.workers.length, busy })}>
      {frame.workers.map((worker, i) => {
        const card = layout.cards[i];
        const [p0, p1, p2, p3] = connector(anchor, { x: card.cx, y: card.y });
        return <path key={worker.id} className={`lv-link lv-link-${worker.state}`} d={`M${p0.x} ${p0.y} C${p1.x} ${p1.y} ${p2.x} ${p2.y} ${p3.x} ${p3.y}`} />;
      })}

      <g className="lv-coordinator">
        <rect x={coordinator.x} y={coordinator.y} width={coordinator.w} height={coordinator.h} rx="14" />
        <text x={coordinator.cx} y={coordinator.y + 30} textAnchor="middle" className="lv-title">{t("Coordinator")}</text>
        <text x={coordinator.cx} y={coordinator.y + 54} textAnchor="middle" className="lv-sub">
          {generation ? fillTemplate(t("Generation {index} of {total}"), { index: generation.index + 1, total: generation.total ?? "?" }) : t("Not started")}
        </text>
        <text x={coordinator.cx} y={coordinator.y + 72} textAnchor="middle" className="lv-sub">
          {fillTemplate(t("{done} of {total} candidates committed"), { done: frame.totals.committed, total: frame.totals.total ?? "?" })}
        </text>
      </g>

      {frame.workers.map((worker, i) => {
        const card = layout.cards[i];
        const progress = worker.job?.progress ?? 0;
        return (
          <g key={worker.id} className={`lv-card lv-card-${worker.state}`}>
            <rect x={card.x} y={card.y} width={card.w} height={card.h} rx="14" />
            <circle className="lv-ring-track" cx={card.x + 44} cy={card.y + 56} r={RING_R} />
            {worker.state === "busy" && <circle className="lv-ring" cx={card.x + 44} cy={card.y + 56} r={RING_R} strokeDasharray={`${CIRC * Math.min(1, Math.max(0, progress))} ${CIRC}`} transform={`rotate(-90 ${card.x + 44} ${card.y + 56})`} />}
            <text x={card.x + 44} y={card.y + 61} textAnchor="middle" className="lv-ring-label">{worker.state === "busy" && worker.job ? candidateLabel(worker.job.candidateId) : worker.state === "unstarted" ? "–" : "●"}</text>
            <text x={card.x + 82} y={card.y + 42} className="lv-worker">{worker.id.length > 16 ? worker.id.slice(0, 15) + "…" : worker.id}</text>
            <text x={card.x + 82} y={card.y + 64} className="lv-state">{stateText(worker, t)}</text>
            <line x1={card.x + 16} x2={card.x + card.w - 16} y1={card.y + 100} y2={card.y + 100} className="lv-rule" />
            <text x={card.x + 16} y={card.y + 124} className="lv-stat">{fillTemplate(t("{n} done"), { n: worker.done })}{worker.failed ? ` · ${fillTemplate(t("{n} failed"), { n: worker.failed })}` : ""}</text>
            <text x={card.x + 16} y={card.y + 144} className="lv-stat lv-muted">{worker.meanSeconds !== null ? fillTemplate(t("{s} s per candidate"), { s: worker.meanSeconds.toFixed(1) }) : t("No result yet")}</text>
          </g>
        );
      })}

      {!reducedMotion && frame.packets.map(packet => {
        const index = frame.workers.findIndex(w => w.id === packet.workerId);
        if (index < 0) return null;
        const card = layout.cards[index];
        const at = packetPosition(packet.kind, packet.progress, anchor, { x: card.cx, y: card.y });
        return (
          <g key={`${packet.candidateId}-${packet.kind}`} className={`lv-packet lv-packet-${packet.kind}`} transform={`translate(${at.x} ${at.y})`}>
            <circle r="9" />
            <text y="-14" textAnchor="middle">{packet.kind === "result" && packet.reward != null ? packet.reward.toFixed(2) : candidateLabel(packet.candidateId)}</text>
          </g>
        );
      })}
    </svg>
  );
}
