import { useProduct } from '@heteroes/product-ui';
import { useRef } from 'react';
import { candidateLabel, formatDuration, niceTicks } from '../../lib/diagramLayout';
import { fillTemplate } from '../../lib/eventText';
import type { Frame, Timeline } from '../../lib/runFrame';

// Start-up moments are drawn as a thin "loading" strip, not as warnings.
const SETUP = new Set(['worker_start', 'model_loaded', 'executor_ready']);

const W = 960,
  LEFT = 92,
  RIGHT = 18,
  TOP = 30,
  LANE = 34,
  BAR = 22;

/** One lane per GPU over time: each block is one attempt at a candidate; the line is the playhead. Click to jump. */
export function RunGantt({
  timeline,
  frame,
  bounds,
  onSeek,
}: {
  timeline: Timeline;
  frame: Frame;
  bounds: { startMs: number; endMs: number };
  onSeek: (atMs: number) => void;
}) {
  const { t } = useProduct();
  const ref = useRef<SVGSVGElement>(null);
  const lanes = timeline.workers.filter((w) => w.started || timeline.jobs.some((j) => j.workerId === w.id));
  const height = TOP + Math.max(1, lanes.length) * LANE + 28;
  // Skip the long wait before anything happens: the axis starts a moment before the first candidate or generation.
  const firsts = [
    ...timeline.jobs.map((j) => j.startMs),
    ...timeline.generations.map((g) => g.openMs).filter((v): v is number => v !== null),
  ];
  const viewStart = firsts.length
    ? Math.min(bounds.endMs, Math.max(bounds.startMs, Math.min(...firsts) - 1500))
    : bounds.startMs;
  const span = Math.max(1, bounds.endMs - viewStart);
  const x = (ms: number) =>
    LEFT + ((Math.min(Math.max(ms, viewStart), bounds.endMs) - viewStart) / span) * (W - LEFT - RIGHT);
  const ticks = niceTicks(viewStart, bounds.endMs, 8);
  const seek = (event: React.PointerEvent) => {
    const box = ref.current?.getBoundingClientRect();
    if (!box || (event.buttons === 0 && event.type === 'pointermove')) return;
    const fraction = (((event.clientX - box.left) / box.width) * W - LEFT) / (W - LEFT - RIGHT);
    onSeek(viewStart + Math.min(1, Math.max(0, fraction)) * span);
  };

  return (
    <svg
      ref={ref}
      className="lv-gantt"
      viewBox={`0 0 ${W} ${height}`}
      role="img"
      aria-label={t('Timeline: one lane per GPU, one block per attempt')}
    >
      {timeline.generations.map((generation, i) => {
        const from = generation.openMs ?? viewStart,
          to = generation.doneMs ?? bounds.endMs;
        return (
          <g key={generation.id} className={i % 2 ? 'lv-band lv-band-odd' : 'lv-band'}>
            <rect x={x(from)} y={TOP - 6} width={Math.max(1, x(to) - x(from))} height={height - TOP - 14} />
            <text x={x(from) + 4} y={TOP - 10}>
              {fillTemplate(t('G{n}'), { n: generation.index + 1 })}
            </text>
            {generation.evaluatedMs !== null && generation.doneMs !== null && (
              <rect
                className="lv-update"
                x={x(generation.evaluatedMs)}
                y={TOP - 6}
                width={Math.max(2, x(generation.doneMs) - x(generation.evaluatedMs))}
                height={height - TOP - 14}
              >
                <title>{t('Update and publish the model')}</title>
              </rect>
            )}
          </g>
        );
      })}

      {ticks.map((tick) => (
        <g key={tick} className="lv-tick">
          <line x1={x(tick)} x2={x(tick)} y1={TOP - 6} y2={height - 20} />
          <text x={x(tick)} y={height - 6} textAnchor="middle">
            {formatDuration(tick - bounds.startMs)}
          </text>
        </g>
      ))}

      {lanes.map((worker, row) => {
        const y = TOP + row * LANE;
        return (
          <g key={worker.id}>
            <text x={LEFT - 10} y={y + BAR / 2 + 4} textAnchor="end" className="lv-lane-name">
              {worker.id.length > 12 ? worker.id.slice(0, 11) + '…' : worker.id}
            </text>
            <line className="lv-lane" x1={LEFT} x2={W - RIGHT} y1={y + BAR + 5} y2={y + BAR + 5} />
            {timeline.jobs
              .filter((job) => job.workerId === worker.id)
              .map((job) => {
                const end = job.endMs ?? bounds.endMs;
                const width = Math.max(3, x(end) - x(job.startMs));
                return (
                  <g
                    key={job.attemptId ?? `${job.candidateId}-${job.startMs}`}
                    className={`lv-job lv-job-${(job.status ?? 'RUNNING').toLowerCase()}`}
                  >
                    <rect x={x(job.startMs)} y={y} width={width} height={BAR} rx="5">
                      <title>{`${candidateLabel(job.candidateId)} · ${job.status ?? ''} · ${formatDuration(end - job.startMs)}${job.reward != null ? ` · reward ${job.reward.toFixed(2)}` : ''}`}</title>
                    </rect>
                    {width > 30 && (
                      <text x={x(job.startMs) + width / 2} y={y + BAR / 2 + 4} textAnchor="middle">
                        {candidateLabel(job.candidateId)}
                      </text>
                    )}
                  </g>
                );
              })}
            {(() => {
              const begin = timeline.marks.find((m) => m.workerId === worker.id && m.type === 'worker_start')?.atMs;
              const ready = timeline.marks.find((m) => m.workerId === worker.id && m.type === 'executor_ready')?.atMs;
              return begin !== undefined && x(ready ?? bounds.endMs) > x(begin) ? (
                <rect
                  className="lv-loading"
                  x={x(begin)}
                  y={y + BAR / 2 - 2}
                  width={Math.max(2, x(ready ?? bounds.endMs) - x(begin))}
                  height="4"
                  rx="2"
                >
                  <title>{t('Loading the model')}</title>
                </rect>
              ) : null;
            })()}
            {timeline.marks
              .filter((mark) => mark.workerId === worker.id && !SETUP.has(mark.type))
              .map((mark) => (
                <path
                  key={`${mark.type}-${mark.atMs}`}
                  className={`lv-mark lv-mark-${mark.type}`}
                  d={`M${x(mark.atMs)} ${y - 4} l5 -8 l-10 0 z`}
                >
                  <title>{mark.type.replace(/_/g, ' ')}</title>
                </path>
              ))}
          </g>
        );
      })}

      <g className="lv-playhead">
        <line x1={x(frame.atMs)} x2={x(frame.atMs)} y1={TOP - 14} y2={height - 20} />
        <circle cx={x(frame.atMs)} cy={TOP - 14} r="5" />
      </g>
      <rect
        className="lv-hit"
        x={LEFT}
        y="0"
        width={W - LEFT - RIGHT}
        height={height}
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          seek(event);
        }}
        onPointerMove={seek}
      />
    </svg>
  );
}
