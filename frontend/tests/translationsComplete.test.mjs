import { test } from 'node:test';
import assert from 'node:assert/strict';
import { translations } from '../../packages/product-ui/src/translations.ts';
import { TEMPLATES } from '../src/lib/notificationText.ts';
import { describeEvent } from '../src/lib/eventText.ts';
import { BUILT_IN } from '../src/lib/templates.ts';
import { GLOSSARY } from '../src/lib/glossary.ts';
import { presentationScenes } from '../src/lib/presentationScenes.ts';

// Texts chosen at run time (tables of sentences) cannot be seen by scripts/check-i18n.mjs, so they are checked here.
const EVENT_TYPES = ['managed_start', 'generation_open', 'generation_complete', 'update_recorded', 'update_applied', 'weights_published', 'generation_done', 'weights_pruned', 'worker_start', 'model_loaded', 'executor_ready', 'replay_policy', 'start', 'replay', 'exit', 'coordinator_recovery', 'recovered', 'generation_resumed', 'transport_error', 'worker_unavailable', 'worker_start_unknown', 'managed_error', 'recovery_point_created', 'recovery_point_error', 'backup_policy_applied', 'step'];

test('every notification sentence has a Vietnamese version with the same placeholders', () => {
    for (const [kind, [template]] of Object.entries(TEMPLATES)) {
        const vi = translations[template];
        assert.ok(vi, `${kind}: ${template}`);
        assert.deepEqual([...template.matchAll(/\{(\w+)\}/g)].map(m => m[1]).sort(), [...vi.matchAll(/\{(\w+)\}/g)].map(m => m[1]).sort(), `${kind} placeholders`);
    }
});

test('every event sentence has a Vietnamese version with the same placeholders', () => {
    for (const type of EVENT_TYPES) for (const details of [{ noop: false }, { noop: true }, { kind: 'COMMITTED' }, { kind: 'NO_WORK' }]) {
        const { template } = describeEvent(type, details, 'w');
        const vi = translations[template];
        assert.ok(vi, `${type}: ${template}`);
        assert.deepEqual([...template.matchAll(/\{(\w+)\}/g)].map(m => m[1]).sort(), [...vi.matchAll(/\{(\w+)\}/g)].map(m => m[1]).sort(), `${type} placeholders`);
    }
});

test('the built-in template names are translated', () => {
    for (const { name } of BUILT_IN) assert.ok(translations[name], name);
});

test('every glossary word and definition is translated', () => {
    for (const [word, definition] of Object.entries(GLOSSARY)) { assert.ok(translations[word], word); assert.ok(translations[definition], definition); }
});

test('every presentation scene label is translated', () => {
    const scenes = presentationScenes([{ experimentId: 'a', status: 'RUNNING', workerIds: ['x'], createdAt: '1' }, { experimentId: 'b', status: 'COMPLETED', workerIds: ['x', 'y'], createdAt: '2' }, { experimentId: 'c', status: 'COMPLETED', workerIds: ['x'], createdAt: '3' }]);
    for (const { label } of scenes) assert.ok(translations[label], label);
    assert.ok(translations['Replay of a real run']);
});
