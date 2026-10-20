import { test } from 'node:test';
import assert from 'node:assert/strict';
import { translations } from '../../packages/product-ui/src/translations.ts';
import { TEMPLATES } from '../src/lib/notificationText.ts';
import { DEVICE_WAITS, describeEvent } from '../src/lib/eventText.ts';
import { BUILT_IN } from '../src/lib/templates.ts';
import { GLOSSARY } from '../src/lib/glossary.ts';
import { presentationScenes } from '../src/lib/presentationScenes.ts';

// Texts chosen at run time (tables of sentences) cannot be seen by scripts/check-i18n.mjs, so they are checked here.
const EVENT_TYPES = [
  'managed_start',
  'generation_open',
  'generation_complete',
  'update_recorded',
  'update_applied',
  'weights_published',
  'generation_done',
  'weights_pruned',
  'worker_start',
  'model_loaded',
  'executor_ready',
  'replay_policy',
  'start',
  'replay',
  'exit',
  'coordinator_recovery',
  'recovered',
  'generation_resumed',
  'transport_error',
  'worker_unavailable',
  'worker_start_unknown',
  'managed_error',
  'recovery_point_created',
  'recovery_point_error',
  'backup_policy_applied',
  'step',
  'agent_command_deferred',
  'agent_command_failed',
];

test('every notification sentence has a Vietnamese version with the same placeholders', () => {
  for (const [kind, [template]] of Object.entries(TEMPLATES)) {
    const vi = translations[template];
    assert.ok(vi, `${kind}: ${template}`);
    assert.deepEqual(
      [...template.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort(),
      [...vi.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort(),
      `${kind} placeholders`,
    );
  }
});

test('every event sentence has a Vietnamese version with the same placeholders', () => {
  for (const type of EVENT_TYPES)
    for (const details of [{ noop: false }, { noop: true }, { kind: 'COMMITTED' }, { kind: 'NO_WORK' }]) {
      const { template } = describeEvent(type, details, 'w');
      const vi = translations[template];
      assert.ok(vi, `${type}: ${template}`);
      assert.deepEqual(
        [...template.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort(),
        [...vi.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort(),
        `${type} placeholders`,
      );
    }
});

test('every reason a device can give for waiting has a Vietnamese sentence with the same placeholders', () => {
  assert.ok(DEVICE_WAITS.size >= 10);
  for (const reason of DEVICE_WAITS.keys()) {
    const { template, params } = describeEvent('agent_command_deferred', { reason }, 'w');
    assert.ok(translations[template], reason);
    assert.deepEqual(Object.keys(params), [], reason);
  }
});

test('the built-in template names are translated', () => {
  for (const { name } of BUILT_IN) assert.ok(translations[name], name);
});

test('every glossary word and definition is translated', () => {
  for (const [word, definition] of Object.entries(GLOSSARY)) {
    assert.ok(translations[word], word);
    assert.ok(translations[definition], definition);
  }
});

test('every presentation scene label is translated', () => {
  const scenes = presentationScenes([
    { experimentId: 'a', status: 'RUNNING', workerIds: ['x'], createdAt: '1' },
    { experimentId: 'b', status: 'COMPLETED', workerIds: ['x', 'y'], createdAt: '2' },
    { experimentId: 'c', status: 'COMPLETED', workerIds: ['x'], createdAt: '3' },
  ]);
  for (const { label } of scenes) assert.ok(translations[label], label);
  assert.ok(translations['Replay of a real run']);
});

test('every readable text in the status tables (labels, tooltips, legends, hints) is translated', async () => {
  const tables = await import('../src/lib/labels.ts');
  const missing = [];
  let checked = 0;
  // `tone` and `status` are identifiers, not text; everything else in these tables is shown to people.
  const walk = (path, value) => {
    if (typeof value === 'string') {
      if (!/[A-Za-z]{3}/.test(value)) return;
      checked++;
      if (!translations[value]) missing.push(`${path}: ${value}`);
    } else if (value && typeof value === 'object') {
      for (const [key, inner] of Object.entries(value))
        if (key !== 'tone' && key !== 'status') walk(`${path}.${key}`, inner);
    }
  };
  for (const [name, value] of Object.entries(tables)) walk(name, value);
  assert.ok(checked > 60, `the walk really visited the tables (${checked} texts)`);
  assert.deepEqual(missing, []);
});
