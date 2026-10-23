import { useProduct } from '@heteroes/product-ui';
import { useMemo } from 'react';
import { candidateLabel, layoutWorkers, workerRoute, routePosition, shortName } from '../../lib/diagramLayout';
import { fillTemplate } from '../../lib/eventText';
import type { Frame, WorkerFrame } from '../../lib/runFrame';

const RING_R = 24;
const CIRC = 2 * Math.PI * RING_R;

function stateText(worker: WorkerFrame, t: (key: string) => string): string {
  if (worker.state === 'busy' && worker.job)
    return fillTemplate(t('Evaluating {candidate}'), { candidate: candidateLabel(worker.job.candidateId) });
  if (worker.state === 'offline') return t('Connection lost');
  if (worker.state === 'blocked') return t('Synchronization blocked');
  if (worker.state === 'unstarted') return t('Not started');
  if (worker.state === 'starting') return t('Loading the model');
  if (worker.state === 'stopped') return t('Stopped');
  return t('Waiting for work');
}

/** Coordinator in the middle of the top, one card per GPU below it, and packets flying along the connectors. */
export function LiveDiagram({
  frame,
  reducedMotion,
  narrow = false,
}: {
  frame: Frame;
  reducedMotion: boolean;
  narrow?: boolean;
}) {
  const { t } = useProduct();
  const layout = useMemo(() => layoutWorkers(frame.workers.length, narrow), [frame.workers.length, narrow]);
  const routes = useMemo(() => layout.cards.map((_, index) => workerRoute(layout, index)), [layout]);
  const { coordinator } = layout;
  const generation = frame.generation;
  const busy = frame.workers.filter((w) => w.state === 'busy').length;

  if (narrow)
    return (
      <div className="hero-flow" aria-label={t('Distributed experiment workflow')}>
        <div className="hero-coordinator">
          <b>{t('Coordinator')}</b>
          <span>{generation ? `${t('Generation')} ${generation.index + 1}` : t('Not started')}</span>
          <small>
            {frame.totals.committed} / {frame.totals.total ?? '—'} {t('Candidates committed')}
          </small>
        </div>
        <div className="hero-gpus">
          {frame.workers.map((worker) => (
            <div className={`hero-gpu ${worker.state}`} key={worker.id}>
              <span className="hero-gpu-dot" aria-hidden="true" />
              <b title={worker.name ?? worker.id}>{worker.name ?? worker.id}</b>
              <span>{stateText(worker, t)}</span>
              <small>
                {worker.done} {t('done')}
              </small>
            </div>
          ))}
        </div>
      </div>
    );

  return (
    <svg
      className="lv-diagram"
      viewBox={`0 0 ${layout.width} ${layout.height}`}
      style={{ minWidth: layout.width }}
      role="img"
      aria-label={fillTemplate(t('Diagram: the coordinator and {count} GPUs, {busy} working'), {
        count: frame.workers.length,
        busy,
      })}
    >
      {frame.workers.map((worker, i) => {
        const route = routes[i];
        return (
          <path
            key={worker.id}
            className={`lv-link lv-link-${worker.state}`}
            d={route.map((p, index) => `${index ? 'L' : 'M'}${p.x} ${p.y}`).join(' ')}
          />
        );
      })}

      <g className="lv-coordinator">
        <rect x={coordinator.x} y={coordinator.y} width={coordinator.w} height={coordinator.h} rx="14" />
        <text x={coordinator.cx} y={coordinator.y + 30} textAnchor="middle" className="lv-title">
          {t('Coordinator')}
        </text>
        <text x={coordinator.cx} y={coordinator.y + 54} textAnchor="middle" className="lv-sub">
          {generation
            ? fillTemplate(t('Generation {index} of {total}'), {
                index: generation.index + 1,
                total: generation.total ?? '?',
              })
            : t('Not started')}
        </text>
        <text x={coordinator.cx} y={coordinator.y + 72} textAnchor="middle" className="lv-sub">
          {fillTemplate(t('{done} of {total} candidates committed'), {
            done: frame.totals.committed,
            total: frame.totals.total ?? '?',
          })}
        </text>
      </g>

      {frame.workers.map((worker, i) => {
        const card = layout.cards[i];
        const progress = worker.job?.progress ?? 0;
        return (
          <g key={worker.id} className={`lv-card lv-card-${worker.state}`}>
            <title>
              {[
                worker.name || worker.id,
                worker.gpuName,
                worker.id,
                worker.state === 'blocked'
                  ? t('Cannot synchronize weights on this connection. Automatic retry is paused temporarily.')
                  : null,
              ]
                .filter(Boolean)
                .join(' · ')}
            </title>
            <rect x={card.x} y={card.y} width={card.w} height={card.h} rx="14" />
            <circle className="lv-ring-track" cx={card.x + 44} cy={card.y + 56} r={RING_R} />
            {worker.state === 'busy' && (
              <circle
                className="lv-ring"
                cx={card.x + 44}
                cy={card.y + 56}
                r={RING_R}
                strokeDasharray={`${CIRC * Math.min(1, Math.max(0, progress))} ${CIRC}`}
                transform={`rotate(-90 ${card.x + 44} ${card.y + 56})`}
              />
            )}
            <text x={card.x + 44} y={card.y + 61} textAnchor="middle" className="lv-ring-label">
              {worker.state === 'busy' && worker.job
                ? candidateLabel(worker.job.candidateId)
                : worker.state === 'unstarted'
                  ? '–'
                  : '●'}
            </text>
            <text x={card.x + 82} y={card.y + 42} className="lv-worker">
              {shortName(worker.name || worker.id, 16)}
            </text>
            <text x={card.x + 82} y={card.y + 64} className="lv-state">
              {stateText(worker, t)}
            </text>
            {worker.gpuName && (
              <text x={card.x + 82} y={card.y + 82} className="lv-state">
                {shortName(worker.gpuName.replace(/^NVIDIA (?:GeForce )?/, ''), 19)}
              </text>
            )}
            <line x1={card.x + 16} x2={card.x + card.w - 16} y1={card.y + 100} y2={card.y + 100} className="lv-rule" />
            <text x={card.x + 16} y={card.y + 124} className="lv-stat">
              {fillTemplate(t('{n} done'), { n: worker.done })}
              {worker.failed ? ` · ${fillTemplate(t('{n} failed'), { n: worker.failed })}` : ''}
            </text>
            <text x={card.x + 16} y={card.y + 144} className="lv-stat lv-muted">
              {worker.meanSeconds !== null
                ? fillTemplate(t('{s} s per candidate'), { s: worker.meanSeconds.toFixed(1) })
                : t('No result yet')}
            </text>
          </g>
        );
      })}

      {!reducedMotion &&
        frame.packets.map((packet) => {
          const index = frame.workers.findIndex((w) => w.id === packet.workerId);
          if (index < 0) return null;
          const route = routes[index];
          const at = routePosition(route, packet.kind === 'dispatch' ? packet.progress : 1 - packet.progress);
          return (
            <g
              key={`${packet.workerId}-${packet.candidateId}-${packet.kind}`}
              className={`lv-packet lv-packet-${packet.kind}`}
              transform={`translate(${at.x} ${at.y})`}
            >
              <circle r="4" />
              <title>
                {packet.kind === 'result' && packet.reward != null
                  ? packet.reward.toFixed(2)
                  : candidateLabel(packet.candidateId)}
              </title>
            </g>
          );
        })}
    </svg>
  );
}
