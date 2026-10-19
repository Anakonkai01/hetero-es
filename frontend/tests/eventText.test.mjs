import { test } from 'node:test';
import assert from 'node:assert/strict';
import { describeEvent, fillTemplate } from '../src/lib/eventText.ts';

test('every event the coordinator records has a plain sentence with its numbers filled in', () => {
  const cases = [
    ['generation_open', { generation: 2, candidates: 8 }, undefined, 'Generation 3 opened with 8 candidates'],
    [
      'generation_done',
      { generation: 0, total_seconds: 15.34, mean_reward: 0.2239583, max_reward: 0.3125 },
      undefined,
      'Generation 1 done in 15.3 s: mean reward 0.2240, best 0.3125',
    ],
    ['update_applied', { generation: 0, noop: false }, undefined, 'Update applied to the model after generation 1'],
    ['update_applied', { generation: 1, noop: true }, undefined, 'Generation 2 left the model unchanged'],
    ['weights_published', { generation: 4 }, undefined, 'New model weights after generation 5 are published'],
    ['worker_start', { worker_id: '5070ti' }, '5070ti', 'Worker 5070ti started'],
    ['model_loaded', { seconds: 1.311 }, '3060', 'Worker 3060 loaded the model in 1.3 s'],
    ['executor_ready', {}, '3060', 'Worker 3060 is ready to evaluate candidates'],
    ['replay', {}, '3060', 'Worker 3060 rebuilt the new weights by replaying the updates'],
    ['exit', { reason: 'finished' }, '3060', 'Worker 3060 finished (finished)'],
    ['worker_unavailable', {}, '3060', 'Worker 3060 is not answering'],
    ['recovery_point_created', { generation: 0 }, undefined, 'Recovery point saved for generation 1'],
    ['recovery_point_error', { generation: 0 }, undefined, 'Could not save a recovery point for generation 1'],
    [
      'backup_policy_applied',
      { policy: { interval: 1, retain: 2 } },
      undefined,
      'Backup policy: every 1 generation(s), keep 2',
    ],
  ];
  for (const [type, details, worker, expected] of cases) {
    const d = describeEvent(type, details, worker);
    assert.equal(fillTemplate(d.template, d.params), expected, type);
  }
});

test('routine chatter is a detail; milestones and problems are main events with the right tone', () => {
  assert.equal(describeEvent('step', { kind: 'NO_WORK' }, '3060').level, 'detail');
  assert.equal(describeEvent('step', { kind: 'COMMITTED', candidate_id: 'abc.g0.c3' }, '3060').level, 'detail');
  for (const type of [
    'generation_open',
    'generation_done',
    'worker_unavailable',
    'managed_error',
    'coordinator_recovery',
    'recovery_point_error',
  ])
    assert.equal(describeEvent(type, {}, 'w').level, 'main', type);
  assert.equal(describeEvent('worker_unavailable', {}, 'w').tone, 'warn');
  assert.equal(describeEvent('managed_error', { error: 'boom' }, undefined).tone, 'err');
  assert.equal(describeEvent('generation_done', {}, undefined).tone, 'ok');
  assert.equal(describeEvent('worker_start', {}, 'w').tone, 'info');
});

test('unknown events fall back to a readable phrase and never throw on missing fields', () => {
  const d = describeEvent('something_new_happened', {}, undefined);
  assert.equal(fillTemplate(d.template, d.params), 'Something new happened');
  assert.equal(d.level, 'detail');
  assert.doesNotThrow(() => describeEvent('generation_done', undefined, undefined));
  assert.equal(
    fillTemplate('Hello {name} {missing}', { name: 'x' }),
    'Hello x',
    'an unknown placeholder disappears and no trailing space is left',
  );
});

test('a recorded error text is carried as a parameter, not baked into the translatable template', () => {
  const d = describeEvent('managed_error', { error: 'ValueError: bad engine' }, undefined);
  assert.ok(!d.template.includes('ValueError'));
  assert.equal(d.params.error, 'ValueError: bad engine');
});
