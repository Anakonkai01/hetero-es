// Turns the coordinator's raw event names into plain sentences. The English template is the translation key
// (looked up with t()); {placeholders} are filled afterwards so numbers never end up inside a translation key.
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
