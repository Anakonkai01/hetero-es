import { test } from 'node:test';
import assert from 'node:assert/strict';
import { describeEvent, deviceNotice, fillTemplate } from '../src/lib/eventText.ts';

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
    [
      'membership_changed',
      { workerId: '1660s', action: 'JOIN', generation: 9 },
      undefined,
      'Worker 1660s joined from generation 10',
    ],
    [
      'membership_changed',
      { workerId: '3060', action: 'LEAVE', generation: 29 },
      undefined,
      'Worker 3060 left from generation 30',
    ],
    [
      'membership_refused',
      { reason: 'the last member cannot leave' },
      undefined,
      'A membership change was refused: the last member cannot leave',
    ],
    ['worker_joined', { worker_id: '1660s' }, '1660s', 'Worker 1660s is starting for this run'],
    ['worker_left', { worker_id: '3060' }, '3060', 'Worker 3060 stopped and left this run'],
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

test('validation rewards have a readable timeline event', () => {
  const event = describeEvent('validation_completed', { generation: 2, meanReward: 0.75 });
  assert.equal(fillTemplate(event.template, event.params), 'Validation after generation 3: reward 0.7500');
});

test('audit mismatches and quarantine are visible without claiming a reward changed', () => {
  const mismatch = describeEvent('audit_mismatch', { worker_id: 'other', candidate_id: 'r/g0/c0' });
  assert.equal(mismatch.tone, 'warn');
  assert.match(fillTemplate(mismatch.template, mismatch.params), /other.*r\/g0\/c0/);
  const quarantine = describeEvent('audit_worker_quarantined', { worker_id: 'original' });
  assert.equal(quarantine.tone, 'err');
});

test('a device that has to wait says why in plain words; a failure carries the agent’s own reason', () => {
  const say = (type, details) => {
    const d = describeEvent(type, details, undefined);
    return [fillTemplate(d.template, d.params), d.tone, d.level];
  };
  assert.deepEqual(say('agent_command_deferred', { reason: 'Contribution is OFF for this boot' }), [
    'This device is waiting: contribution is switched off on it',
    'warn',
    'main',
  ]);
  assert.deepEqual(say('agent_command_deferred', { reason: 'A newer agent message' }), [
    'A device is waiting to carry out a command: A newer agent message',
    'warn',
    'main',
  ]);
  assert.deepEqual(say('agent_command_deferred', {}), [
    'A device is waiting to carry out a command: ?',
    'warn',
    'main',
  ]);
  // a name every object inherits is not one of the known reasons
  assert.equal(
    say('agent_command_deferred', { reason: 'constructor' })[0],
    'A device is waiting to carry out a command: constructor',
  );
  assert.deepEqual(say('agent_command_failed', { reason: 'Invalid run identity', errorType: 'InvalidCommand' }), [
    'A device could not carry out a command: Invalid run identity',
    'err',
    'main',
  ]);
  assert.deepEqual(say('agent_command_failed', { errorType: 'OSError' }), [
    'A device could not carry out a command (OSError)',
    'err',
    'main',
  ]);
  assert.equal(say('agent_command_failed', {})[0], 'A device could not carry out a command (?)');
});

test('the newest device message explains a run that is starting or running, until the coordinator speaks', () => {
  const event = (eventType, timestamp, details = {}) => ({
    eventId: eventType + timestamp,
    timestamp,
    eventType,
    severity: 'INFO',
    message: '',
    details,
  });
  const early = event('generation_done', '2026-10-20T10:00:00+00:00');
  const wait = event('agent_command_deferred', '2026-10-20T10:01:00+00:00', {
    reason: 'Contribution is OFF for this boot',
  });
  const failed = event('agent_command_failed', '2026-10-20T10:02:00+00:00', { reason: 'Invalid run identity' });
  const later = event('managed_start', '2026-10-20T10:03:00+00:00');

  const notice = deviceNotice('STARTING', [early, wait]);
  assert.equal(notice?.timestamp, wait.timestamp);
  assert.equal(
    fillTemplate(notice.template, notice.params),
    'This device is waiting: contribution is switched off on it',
  );
  assert.equal(notice.tone, 'warn');
  assert.equal(deviceNotice('RUNNING', [wait])?.timestamp, wait.timestamp);
  assert.equal(deviceNotice('STARTING', [wait, failed])?.tone, 'err', 'the newest one wins');
  for (const status of ['QUEUED', 'DRAFT', 'PAUSED', 'COMPLETED', 'FAILED', 'CANCELLED'])
    assert.equal(deviceNotice(status, [wait]), null, status);
  assert.equal(deviceNotice('RUNNING', [wait, later]), null, 'the coordinator spoke after the device');
  assert.equal(deviceNotice('STARTING', [early]), null);
  assert.equal(deviceNotice('STARTING', []), null);
});
