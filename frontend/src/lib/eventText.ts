// Turns the coordinator's raw event names into plain sentences. The English template is the translation key
// (looked up with t()); {placeholders} are filled afterwards so numbers never end up inside a translation key.
import type { SystemEvent } from '../types/event';

export type EventDescription = {
  template: string;
  params: Record<string, string | number>;
  level: 'main' | 'detail';
  tone: 'ok' | 'info' | 'warn' | 'err' | 'neutral';
};
type Details = Record<string, unknown> | undefined;

const num = (value: unknown, digits: number) =>
  typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '?';
// Generations are numbered from 0 in the data and from 1 for people.
const gen = (value: unknown) => (typeof value === 'number' ? value + 1 : '?');
const text = (value: unknown) => (typeof value === 'string' ? value : '');

// Why a device's agent keeps a command waiting. The keys are the agent's fixed messages; the sentences are translation
// keys. A message not listed here (a newer agent) is shown in the agent's own words.
export const DEVICE_WAITS = new Map([
  ['Contribution is OFF for this boot', 'This device is waiting: contribution is switched off on it'],
  ['Wait for model probe GPU release before training', 'This device is waiting for a model check to release its GPU'],
  ['Coordinator launch ownership is unknown', 'This device cannot yet tell whether its coordinator is still running'],
  ['Worker launch ownership is unknown', 'This device cannot yet tell whether its worker is still running'],
  ['The coordinator is not reachable on any route yet', 'A worker device cannot reach the coordinator yet'],
  ['No unique active assignment', 'This device cannot tell yet which run it should serve'],
  [
    'Resume requires confirmed paused coordinator shutdown',
    'This device is waiting for the paused coordinator to stop before resuming',
  ],
  ['Resume requires confirmed worker shutdown', 'This device is waiting for its worker to stop before resuming'],
  ['Desktop shutdown is pending', 'This device is shutting down and will not start new work'],
  [
    'Wait for the assignment before applying its policy',
    'This device is waiting for the run assignment before it applies the backup policy',
  ],
  ['another run still owns the GPU pool', 'Another run still holds the GPU, so this run waits'],
]);

export function fillTemplate(template: string, params: Record<string, string | number>): string {
  return template
    .replace(/\{(\w+)\}/g, (_whole, name: string) => (name in params ? String(params[name]) : ''))
    .replace(/\s+$/, '');
}

export function describeEvent(type: string, details: Details, workerId?: string): EventDescription {
  const d = details ?? {};
  const worker = text(d.worker_id) || workerId || '?';
  const done = (
    template: string,
    params: Record<string, string | number> = {},
    tone: EventDescription['tone'] = 'info',
    level: EventDescription['level'] = 'main',
  ): EventDescription => ({ template, params, level, tone });
  switch (type) {
    case 'membership_changed':
      return done(
        d.action === 'LEAVE'
          ? 'Worker {worker} left from generation {generation}'
          : 'Worker {worker} joined from generation {generation}',
        { worker: text(d.workerId) || worker, generation: gen(d.generation) },
      );
    case 'membership_refused':
      return done('A membership change was refused: {reason}', { reason: text(d.reason) || '?' }, 'warn');
    case 'worker_joined':
      return d.rejoin
        ? done('Worker {worker} was added back and is starting again', { worker })
        : done('Worker {worker} is starting for this run', { worker });
    case 'worker_restarted':
      return done('Worker {worker} stopped and is being started again', { worker }, 'warn');
    case 'worker_unreachable':
      return done('Worker {worker} has not answered for 2 minutes', { worker }, 'warn');
    case 'worker_reachable':
      return done('Worker {worker} answers again', { worker });
    case 'worker_lost':
      return done('Worker {worker} was given up as lost', { worker }, 'err');
    case 'worker_left':
      return done('Worker {worker} stopped and left this run', { worker });
    case 'audit_mismatch':
      return done(
        'Audit on {worker} disagreed for {candidate}; committed reward is unchanged',
        { worker, candidate: text(d.candidate_id) },
        'warn',
      );
    case 'audit_worker_quarantined':
      return done('Worker {worker} quarantined after repeated audit mismatches', { worker }, 'err');
    case 'audit_completed':
      return done('Worker {worker} reproduced the committed texts', { worker }, 'ok', 'detail');
    case 'audit_incomplete':
      return done(
        'Generation {generation} has {pending} audits awaiting another available worker',
        { generation: gen(d.generation), pending: typeof d.pending === 'number' ? d.pending : '?' },
        'warn',
      );
    case 'validation_completed':
      return done('Validation after generation {generation}: reward {reward}', {
        generation: gen(d.generation),
        reward: num(d.meanReward, 4),
      });
    case 'managed_start':
      return done('The coordinator started this experiment');
    case 'generation_open':
      return done('Generation {generation} opened with {candidates} candidates', {
        generation: gen(d.generation),
        candidates: typeof d.candidates === 'number' ? d.candidates : '?',
      });
    case 'generation_complete':
      return done(
        'All candidates of generation {generation} are scored',
        { generation: gen(d.generation) },
        'info',
        'detail',
      );
    case 'update_recorded':
      return done(
        'Update record for generation {generation} saved',
        { generation: gen(d.generation) },
        'info',
        'detail',
      );
    case 'update_applied':
      return d.noop === true
        ? done('Generation {generation} left the model unchanged', { generation: gen(d.generation) }, 'neutral')
        : done('Update applied to the model after generation {generation}', { generation: gen(d.generation) });
    case 'weights_published':
      return done(
        'New model weights after generation {generation} are published',
        { generation: gen(d.generation) },
        'info',
        'detail',
      );
    case 'generation_done':
      return done(
        'Generation {generation} done in {seconds} s: mean reward {mean}, best {best}',
        {
          generation: gen(d.generation),
          seconds: num(d.total_seconds, 1),
          mean: num(d.mean_reward, 4),
          best: num(d.max_reward, 4),
        },
        'ok',
      );
    case 'weights_pruned':
      return done('Old model weights cleaned up', {}, 'neutral', 'detail');
    case 'worker_start':
      return done('Worker {worker} started', { worker });
    case 'model_loaded':
      return done('Worker {worker} loaded the model in {seconds} s', { worker, seconds: num(d.seconds, 1) });
    case 'executor_ready':
      return done('Worker {worker} is ready to evaluate candidates', { worker });
    case 'replay_policy':
      return done(
        'Worker {worker} state-sync policy: {mode}',
        { worker, mode: text((d.policy as { mode?: unknown } | undefined)?.mode) || '?' },
        'neutral',
        'detail',
      );
    case 'start':
      return done('Worker {worker} started taking work', { worker }, 'info', 'detail');
    case 'replay':
      return done('Worker {worker} rebuilt the new weights by replaying the updates', { worker }, 'info', 'detail');
    case 'exit':
      return done('Worker {worker} finished ({reason})', { worker, reason: text(d.reason) || '?' }, 'neutral');
    case 'coordinator_recovery':
      return done(
        'The coordinator recovered after an interruption (recovery {count})',
        { count: typeof d.recoveryCount === 'number' ? d.recoveryCount : '?' },
        'warn',
      );
    case 'recovered':
      return done(
        'Recovered at generation {generation}: {action}',
        { generation: gen(d.generation), action: text(d.action) || '?' },
        'warn',
      );
    case 'generation_resumed':
      return done('Generation {generation} resumed', { generation: gen(d.generation) }, 'warn');
    case 'transport_error':
      return done('Could not reach worker {worker}', { worker }, 'err');
    case 'worker_unavailable':
      return done('Worker {worker} is not answering', { worker }, 'warn');
    case 'worker_start_unknown':
      return done('Could not confirm whether worker {worker} started', { worker }, 'warn');
    case 'managed_error':
      return done('The coordinator reported an error: {error}', { error: text(d.error) || '?' }, 'err');
    case 'recovery_point_created':
      return done(
        'Recovery point saved for generation {generation}',
        { generation: gen(d.generation) },
        'info',
        'detail',
      );
    case 'recovery_point_error':
      return done(
        'Could not save a recovery point for generation {generation}',
        { generation: gen(d.generation) },
        'err',
      );
    case 'backup_policy_applied': {
      const policy = (d.policy ?? {}) as { interval?: unknown; retain?: unknown };
      return done(
        'Backup policy: every {interval} generation(s), keep {retain}',
        {
          interval: typeof policy.interval === 'number' ? policy.interval : '?',
          retain: typeof policy.retain === 'number' ? policy.retain : '?',
        },
        'neutral',
        'detail',
      );
    }
    case 'agent_command_deferred': {
      const reason = text(d.reason);
      const known = DEVICE_WAITS.get(reason);
      return known
        ? done(known, {}, 'warn')
        : done('A device is waiting to carry out a command: {reason}', { reason: reason || '?' }, 'warn');
    }
    case 'agent_command_failed':
      return text(d.reason)
        ? done('A device could not carry out a command: {reason}', { reason: text(d.reason) }, 'err')
        : done('A device could not carry out a command ({error})', { error: text(d.errorType) || '?' }, 'err');
    case 'step':
      return d.kind === 'COMMITTED'
        ? done('Worker {worker} committed a candidate', { worker }, 'info', 'detail')
        : done('Worker {worker} asked for work; none was available', { worker }, 'neutral', 'detail');
    default: {
      const phrase = type.replace(/_/g, ' ').trim();
      return done(phrase ? phrase[0].toUpperCase() + phrase.slice(1) : 'Event', {}, 'neutral', 'detail');
    }
  }
}

/** The device message that explains why a run has not got going: only while the run is starting or running, and only
 * while it is the newest thing known about the run (anything the coordinator says afterwards means it got going).
 * `events` are oldest first, as the API returns them. */
export function deviceNotice(status: string, events: SystemEvent[]): (EventDescription & { timestamp: string }) | null {
  const newest = events[events.length - 1];
  if (!newest || !['STARTING', 'RUNNING'].includes(status)) return null;
  if (newest.eventType !== 'agent_command_deferred' && newest.eventType !== 'agent_command_failed') return null;
  return { ...describeEvent(newest.eventType, newest.details, newest.workerId), timestamp: newest.timestamp };
}
