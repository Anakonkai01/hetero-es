// What the Live, Timeline and Replay screens draw: given a run's timeline (see backend/timeline.py) and a point in
// time, say what every GPU is doing, which phase the generation is in and which packets are in flight.
// Pure functions only, so a finished run (replay) and a running one (live) go through exactly the same code.

export type TimelineJob = {
  candidateId: string | null;
  attemptId: string | null;
  generation: number | null;
  workerId: string | null;
  startMs: number;
  endMs: number | null;
  status: string | null;
  reward: number | null;
  seed?: string | null;
};
export type TimelineGeneration = {
  index: number;
  id: string;
  status: string | null;
  openMs: number | null;
  evaluatedMs: number | null;
  doneMs: number | null;
  candidateCount: number | null;
  committedCount: number | null;
  rewardMean: number | null;
  rewardBest: number | null;
  seconds: Record<string, number>;
};
export type TimelineMark = {
  atMs: number;
  type: string;
  workerId: string | null;
  generation: number | null;
  detail?: string;
};
export type Timeline = {
  experiment: {
    id: string;
    name: string;
    status: string | null;
    createdMs: number | null;
    startedMs: number | null;
    completedMs: number | null;
    maxGenerations: number | null;
    candidatesPerGeneration: number | null;
  };
  workers: {
    id: string;
    name?: string | null;
    gpuName?: string | null;
    started: boolean;
    alive: boolean | null;
    unreachableSinceMs?: number | null;
    stopReason?: string | null;
    blockedAtMs?: number | null;
  }[];
  generations: TimelineGeneration[];
  jobs: TimelineJob[];
  marks: TimelineMark[];
  nowMs: number;
  history?: {
    partial: boolean;
    detailedStartMs: number | null;
    firstDetailedGeneration?: number | null;
    lastDetailedGeneration?: number | null;
  };
};

export type WorkerFrame = {
  id: string;
  name: string | null;
  gpuName?: string | null;
  stopReason?: string | null;
  state: 'unstarted' | 'starting' | 'idle' | 'busy' | 'offline' | 'blocked' | 'stopped';
  job?: { candidateId: string; generation: number | null; progress: number; startMs: number };
  done: number;
  failed: number;
  meanSeconds: number | null;
  lastReward: number | null;
};
export type Packet = {
  kind: 'dispatch' | 'result' | 'failed';
  workerId: string;
  candidateId: string;
  progress: number;
  reward?: number | null;
};
export type GenerationFrame = {
  index: number;
  id: string;
  total: number | null;
  committed: number | null;
  count: number | null;
  phase: 'evaluating' | 'updating' | 'between' | 'finished' | 'stopped';
  phaseProgress: number;
  rewardMean: number | null;
  rewardBest: number | null;
};
export type Frame = {
  atMs: number;
  workers: WorkerFrame[];
  generation: GenerationFrame | null;
  packets: Packet[];
  marks: TimelineMark[];
  totals: { committed: number; total: number | null };
  rewards: { generation: number; mean: number; best: number }[];
};

const RUNNING_CAP = 0.95; // a job with no end yet never looks finished
const MARK_VISIBLE_MS = 4000; // how long a notable moment stays on screen
const TERMINAL = new Set(['COMPLETED', 'CANCELLED', 'FAILED']);

const PRESENCE = new Set([
  'worker_unreachable',
  'worker_lost',
  'worker_reachable',
  'worker_restarted',
  'worker_joined',
]);

/** Not answering at that moment: the coordinator's last presence mark for it says so, or it is not answering now
 * (an old mark may have been dropped from a long run's snapshot). Finding 11. */
function isUnreachable(timeline: Timeline, w: Timeline['workers'][number], atMs: number): boolean {
  const last = timeline.marks.filter((m) => m.workerId === w.id && m.atMs <= atMs && PRESENCE.has(m.type)).at(-1);
  if (last) return last.type === 'worker_unreachable' || last.type === 'worker_lost';
  return w.unreachableSinceMs != null && atMs - w.unreachableSinceMs >= 120_000;
}

/** A worker process that has been launched but has not reported ready yet (it is loading the model). */
function isStarting(marks: TimelineMark[], workerId: string, atMs: number): boolean {
  const mine = marks.filter((m) => m.workerId === workerId && m.atMs <= atMs);
  return mine.some((m) => m.type === 'worker_start') && !mine.some((m) => m.type === 'executor_ready');
}

export function runBounds(timeline: Timeline): { startMs: number; endMs: number } {
  const e = timeline.experiment;
  const times = [
    e.startedMs,
    e.createdMs,
    ...timeline.jobs.map((j) => j.startMs),
    ...timeline.generations.map((g) => g.openMs),
  ].filter((v): v is number => typeof v === 'number');
  const startMs = e.startedMs ?? (times.length ? Math.min(...times) : timeline.nowMs);
  const lastKnown = Math.max(
    startMs,
    ...timeline.jobs.map((j) => j.endMs ?? j.startMs),
    ...timeline.generations.map((g) => g.doneMs ?? g.openMs ?? 0),
  );
  const endMs = e.completedMs ?? Math.max(timeline.nowMs, lastKnown);
  return { startMs, endMs };
}

export function frameAt(timeline: Timeline, atMs: number, options: { flightMs?: number } = {}): Frame {
  const flightMs = options.flightMs ?? 700;
  const finished = timeline.jobs.filter((j) => j.endMs !== null && j.endMs <= atMs);
  const committedByGeneration = new Map<number | null, number>();
  for (const job of finished) {
    if (job.status === 'SUCCEEDED')
      committedByGeneration.set(job.generation, (committedByGeneration.get(job.generation) ?? 0) + 1);
  }
  const stopped =
    TERMINAL.has(timeline.experiment.status ?? '') &&
    timeline.experiment.completedMs != null &&
    atMs >= timeline.experiment.completedMs;

  const workers: WorkerFrame[] = timeline.workers.map((w) => {
    const mine = timeline.jobs.filter((j) => j.workerId === w.id);
    const succeeded = finished.filter((j) => j.workerId === w.id && j.status === 'SUCCEEDED');
    const failed = finished.filter((j) => j.workerId === w.id && j.status === 'FAILED');
    const durations = timeline.jobs
      .filter((j) => j.workerId === w.id && j.endMs !== null && j.endMs <= atMs && j.status === 'SUCCEEDED')
      .map((j) => (j.endMs! - j.startMs) / 1000);
    const current = mine.find((j) => j.startMs <= atMs && (j.endMs === null || atMs < j.endMs));
    const frame: WorkerFrame = {
      id: w.id,
      name: w.name ?? null,
      gpuName: w.gpuName,
      stopReason: w.stopReason,
      state: 'idle',
      done: succeeded.length,
      failed: failed.length,
      meanSeconds: durations.length ? durations.reduce((a, b) => a + b, 0) / durations.length : null,
      lastReward: succeeded.length ? [...succeeded].sort((a, b) => a.endMs! - b.endMs!).at(-1)!.reward : null,
    };
    const blockMark = timeline.marks
      .filter(
        (m) =>
          m.workerId === w.id &&
          m.atMs <= atMs &&
          ['worker_blocked', 'worker_retry_requested', 'worker_restarted', 'worker_joined'].includes(m.type),
      )
      .at(-1);
    const blocked =
      blockMark && blockMark.atMs >= (w.blockedAtMs ?? -Infinity)
        ? blockMark.type === 'worker_blocked'
        : w.stopReason === 'needs_private_route' && w.blockedAtMs != null && atMs >= w.blockedAtMs;
    if (stopped && w.started) {
      frame.state = 'stopped';
    } else if (blocked) {
      frame.state = 'blocked';
    } else if (isUnreachable(timeline, w, atMs)) {
      frame.state = 'offline';
    } else if (current) {
      const expected = current.endMs !== null ? current.endMs - current.startMs : (frame.meanSeconds ?? 5) * 1000;
      const raw = expected > 0 ? (atMs - current.startMs) / expected : 0;
      frame.state = 'busy';
      frame.job = {
        candidateId: current.candidateId ?? '',
        generation: current.generation,
        progress: current.endMs !== null ? raw : Math.min(raw, RUNNING_CAP),
        startMs: current.startMs,
      };
    } else if (!w.started) {
      frame.state = 'unstarted';
    } else if (isStarting(timeline.marks, w.id, atMs)) {
      frame.state = 'starting';
    } else if (
      timeline.marks.some(
        (m) =>
          m.workerId === w.id && m.type === 'worker_unavailable' && m.atMs <= atMs && atMs - m.atMs < MARK_VISIBLE_MS,
      )
    ) {
      frame.state = 'offline';
    }
    return frame;
  });

  const opened = timeline.generations.filter((g) => g.openMs !== null && g.openMs <= atMs);
  const current = opened.at(-1);
  let generation: GenerationFrame | null = null;
  if (current) {
    const observedCommitted = committedByGeneration.get(current.index) ?? 0;
    const committed =
      stopped || (current.doneMs !== null && atMs >= current.doneMs)
        ? (current.committedCount ?? observedCommitted)
        : observedCommitted;
    let phase: GenerationFrame['phase'] = 'evaluating';
    let phaseProgress = 0;
    if (stopped && timeline.experiment.status !== 'COMPLETED') {
      phase = 'stopped';
    } else if (current.doneMs !== null && atMs >= current.doneMs) {
      // "finished" only when no further generation can follow: it was the last one planned, or the run has stopped.
      const isLast = current.index + 1 >= (timeline.experiment.maxGenerations ?? Infinity);
      const stopped =
        TERMINAL.has(timeline.experiment.status ?? '') &&
        !timeline.generations.some((g) => g.index === current.index + 1);
      phase = isLast || stopped ? 'finished' : 'between';
      phaseProgress = 1;
    } else if (current.evaluatedMs !== null && atMs >= current.evaluatedMs) {
      phase = 'updating';
      const span = (current.doneMs ?? atMs) - current.evaluatedMs;
      phaseProgress = span > 0 ? Math.min((atMs - current.evaluatedMs) / span, 1) : 0;
    } else if (current.evaluatedMs !== null && current.openMs !== null) {
      phaseProgress = Math.min((atMs - current.openMs) / Math.max(current.evaluatedMs - current.openMs, 1), 1);
    }
    generation = {
      index: current.index,
      id: current.id,
      total: timeline.experiment.maxGenerations,
      committed,
      count: current.candidateCount,
      phase,
      phaseProgress,
      rewardMean: current.rewardMean,
      rewardBest: current.rewardBest,
    };
  }

  const packets: Packet[] = [];
  for (const job of timeline.jobs) {
    if (!job.workerId || !job.candidateId) continue;
    if (atMs >= job.startMs && atMs < job.startMs + flightMs)
      packets.push({
        kind: 'dispatch',
        workerId: job.workerId,
        candidateId: job.candidateId,
        progress: (atMs - job.startMs) / flightMs,
      });
    if (job.endMs !== null && atMs >= job.endMs && atMs < job.endMs + flightMs)
      packets.push({
        kind: job.status === 'FAILED' ? 'failed' : 'result',
        workerId: job.workerId,
        candidateId: job.candidateId,
        progress: (atMs - job.endMs) / flightMs,
        reward: job.reward,
      });
  }

  const rewards = timeline.generations
    .filter((g) => g.doneMs !== null && g.doneMs <= atMs && g.rewardMean !== null && g.rewardBest !== null)
    .map((g) => ({ generation: g.index, mean: g.rewardMean!, best: g.rewardBest! }));

  return {
    atMs,
    workers,
    generation,
    packets,
    marks: timeline.marks.filter((m) => m.atMs <= atMs && atMs - m.atMs < MARK_VISIBLE_MS),
    totals: {
      committed: timeline.generations.reduce(
        (total, g) =>
          total +
          (stopped || (g.doneMs !== null && g.doneMs <= atMs)
            ? (g.committedCount ?? 0)
            : (committedByGeneration.get(g.index) ?? 0)),
        0,
      ),
      total:
        timeline.experiment.maxGenerations && timeline.experiment.candidatesPerGeneration
          ? timeline.experiment.maxGenerations * timeline.experiment.candidatesPerGeneration
          : null,
    },
    rewards,
  };
}

export type PlayerState = { atMs: number; playing: boolean; speed: number };

/** Where a replay begins: at the start, playing. Someone who watched the run live and saw it end stays on the finished picture instead of being thrown back. */
export function replayStart(
  bounds: { startMs: number; endMs: number },
  afterLive: boolean,
  speed: number,
): PlayerState {
  return afterLive ? { atMs: bounds.endMs, playing: false, speed } : { atMs: bounds.startMs, playing: true, speed };
}

/** Moves the playhead by real elapsed time times the speed; it stops at the end and never goes before the start. */
export function advance(
  state: PlayerState,
  elapsedMs: number,
  bounds: { startMs: number; endMs: number },
): PlayerState {
  if (!state.playing) return state;
  const next = Math.max(bounds.startMs, Math.min(bounds.endMs, state.atMs + elapsedMs * state.speed));
  return { ...state, atMs: next, playing: next < bounds.endMs };
}

/** A streamed timeline replaces the previous one unless it is older (messages can arrive out of order after a reconnect). */
export function applyDelta(previous: Timeline | undefined, incoming: Timeline): Timeline {
  return previous && previous.nowMs > incoming.nowMs ? previous : incoming;
}
