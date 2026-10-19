import { test } from 'node:test';
import assert from 'node:assert/strict';
import { presentationScenes } from '../src/lib/presentationScenes.ts';

const run = (id, status, workers, createdAt = '2026-10-10T00:00:00Z') => ({
  experimentId: id,
  status,
  workerIds: workers,
  createdAt,
});

test('the tour starts at the control room and ends with the explanation', () => {
  const scenes = presentationScenes([]);
  assert.deepEqual(
    scenes.map((s) => s.to),
    ['/dashboard', '/explain'],
  );
});

test('the showcase is the run in progress, or else the finished run that used the most GPUs', () => {
  const finished = [
    run('a', 'COMPLETED', ['x']),
    run('b', 'COMPLETED', ['x', 'y', 'z']),
    run('c', 'COMPLETED', ['x', 'y']),
  ];
  assert.equal(presentationScenes(finished)[1].to, '/experiments/b?tab=live');
  assert.equal(presentationScenes(finished)[1].label, 'Replay of a real run');
  const live = presentationScenes([...finished, run('d', 'RUNNING', ['x'])]);
  assert.equal(live[1].to, '/experiments/d?tab=live');
  assert.equal(live[1].label, 'Live view');
});

test('a comparison scene needs two finished runs and uses the two most telling ones', () => {
  assert.equal(
    presentationScenes([run('a', 'COMPLETED', ['x'])]).some((s) => s.label === 'Comparison'),
    false,
  );
  const scenes = presentationScenes([
    run('a', 'COMPLETED', ['x']),
    run('b', 'COMPLETED', ['x', 'y', 'z']),
    run('c', 'COMPLETED', ['x', 'y']),
    run('d', 'FAILED', ['x', 'y', 'z', 'w']),
  ]);
  assert.equal(scenes.find((s) => s.label === 'Comparison').to, '/experiments/compare?ids=b,c');
  assert.deepEqual(scenes.map((s) => s.to).slice(-1), ['/explain']);
});

test('ties go to the newest run', () => {
  const scenes = presentationScenes([
    run('old', 'COMPLETED', ['x', 'y'], '2026-10-01T00:00:00Z'),
    run('new', 'COMPLETED', ['x', 'y'], '2026-10-12T00:00:00Z'),
  ]);
  assert.equal(scenes[1].to, '/experiments/new?tab=live');
});
