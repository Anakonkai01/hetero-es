import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { frameAt, runBounds, advance, applyDelta } from '../src/lib/runFrame.ts';

const real = JSON.parse(fs.readFileSync(new URL('./fixtures/run-fifo.timeline.json', import.meta.url), 'utf8'));
const T0 = 1_000_000;
// Two workers, one generation of four candidates: a is faster than b; c0 on a, c1 on b, c2 on a, c3 on b.
function synthetic(overrides = {}) {
    return {
        experiment: { id: 'r', name: 'run', status: 'RUNNING', createdMs: T0 - 5000, startedMs: T0, completedMs: null, maxGenerations: 2, candidatesPerGeneration: 4 },
        workers: [{ id: 'a', started: true, alive: true }, { id: 'b', started: true, alive: true }, { id: 'c', started: false, alive: false }],
        generations: [{ index: 0, id: 'r.g0', status: 'COMPLETED', openMs: T0 + 1000, evaluatedMs: T0 + 9000, doneMs: T0 + 11000, candidateCount: 4, committedCount: 4, rewardMean: 0.3, rewardBest: 0.5, seconds: { update: 1.5, publish: 0.5, total: 10 } },
            { index: 1, id: 'r.g1', status: 'RUNNING', openMs: T0 + 12000, evaluatedMs: null, doneMs: null, candidateCount: 4, committedCount: 0, rewardMean: null, rewardBest: null, seconds: {} }],
        jobs: [
            { candidateId: 'c0', attemptId: 'c0.a1', generation: 0, workerId: 'a', startMs: T0 + 1000, endMs: T0 + 3000, status: 'SUCCEEDED', reward: 0.25 },
            { candidateId: 'c1', attemptId: 'c1.a1', generation: 0, workerId: 'b', startMs: T0 + 1000, endMs: T0 + 5000, status: 'SUCCEEDED', reward: 0.5 },
            { candidateId: 'c2', attemptId: 'c2.a1', generation: 0, workerId: 'a', startMs: T0 + 3000, endMs: T0 + 4000, status: 'FAILED', reward: null },
            { candidateId: 'c2', attemptId: 'c2.a2', generation: 0, workerId: 'a', startMs: T0 + 5000, endMs: T0 + 7000, status: 'SUCCEEDED', reward: 0.2 },
            { candidateId: 'c3', attemptId: 'c3.a1', generation: 0, workerId: 'b', startMs: T0 + 5000, endMs: T0 + 9000, status: 'SUCCEEDED', reward: 0.25 },
            { candidateId: 'd0', attemptId: 'd0.a1', generation: 1, workerId: 'a', startMs: T0 + 12500, endMs: null, status: 'RUNNING', reward: null },
        ],
        marks: [{ atMs: T0 + 6000, type: 'worker_unavailable', workerId: 'b', generation: null }],
        nowMs: T0 + 13000, ...overrides,
    };
}
const worker = (frame, id) => frame.workers.find(w => w.id === id);

test('before the run nothing is happening; each worker is idle, and an unstarted worker says so', () => {
    const frame = frameAt(synthetic(), T0 - 100);
    assert.equal(frame.generation, null);
    assert.deepEqual(frame.workers.map(w => [w.id, w.state]), [['a', 'idle'], ['b', 'idle'], ['c', 'unstarted']]);
    assert.equal(frame.totals.committed, 0);
});

test('a busy worker shows its candidate with a progress that follows the clock', () => {
    const frame = frameAt(synthetic(), T0 + 2000);
    assert.equal(worker(frame, 'a').state, 'busy');
    assert.equal(worker(frame, 'a').job.candidateId, 'c0');
    assert.equal(worker(frame, 'a').job.progress, 0.5);
    assert.equal(worker(frame, 'b').job.progress, 0.25);
    assert.equal(frame.generation.index, 0);
    assert.equal(frame.generation.phase, 'evaluating');
});

test('finished jobs are counted per worker; a failed attempt counts as failed and not as done', () => {
    const frame = frameAt(synthetic(), T0 + 8000);
    assert.equal(worker(frame, 'a').done, 2);
    assert.equal(worker(frame, 'a').failed, 1);
    assert.equal(worker(frame, 'b').done, 1);
    assert.equal(frame.totals.committed, 3);
    assert.equal(worker(frame, 'a').lastReward, 0.2);
    assert.equal(worker(frame, 'a').meanSeconds, 2);
});

test('the generation moves through evaluating, updating the model and finished before the next opens', () => {
    const synth = synthetic();
    assert.equal(frameAt(synth, T0 + 500).generation, null, 'not opened yet');
    assert.equal(frameAt(synth, T0 + 9500).generation.phase, 'updating');
    assert.equal(frameAt(synth, T0 + 9500).generation.phaseProgress, 0.25);
    assert.equal(frameAt(synth, T0 + 11500).generation.phase, 'between');
    const next = frameAt(synth, T0 + 12600);
    assert.equal(next.generation.index, 1);
    assert.equal(next.generation.phase, 'evaluating');
    assert.equal(next.generation.count, 4);
});

test('between two generations of a live run the screen says so instead of "finished"', () => {
    const live = synthetic({ generations: [synthetic().generations[0]], jobs: synthetic().jobs.slice(0, 5), nowMs: T0 + 11500 });
    assert.equal(frameAt(live, T0 + 11500).generation.phase, 'between', 'generation 2 has not opened yet but the run goes on');
    const lastOfTwo = synthetic({ generations: [synthetic().generations[0], { ...synthetic().generations[1], status: 'COMPLETED', evaluatedMs: T0 + 18000, doneMs: T0 + 19000, committedCount: 4 }], experiment: { ...synthetic().experiment, status: 'COMPLETED', completedMs: T0 + 19500 } });
    assert.equal(frameAt(lastOfTwo, T0 + 19200).generation.phase, 'finished');
    const cancelled = synthetic({ generations: [synthetic().generations[0]], experiment: { ...synthetic().experiment, status: 'CANCELLED', completedMs: T0 + 12000, maxGenerations: 5 } });
    assert.equal(frameAt(cancelled, T0 + 11500).generation.phase, 'finished', 'a stopped run does not wait for a next generation');
});

test('the last planned generation reads finished as soon as it is done, even before the run is marked complete', () => {
    const live = synthetic({ generations: [synthetic().generations[0]], experiment: { ...synthetic().experiment, status: 'RUNNING', maxGenerations: 1 } });
    assert.equal(frameAt(live, T0 + 11500).generation.phase, 'finished');
});

test('a running job with no end yet keeps moving but never claims to be finished', () => {
    const frame = frameAt(synthetic(), T0 + 20000);
    const job = worker(frame, 'a').job;
    assert.equal(job.candidateId, 'd0');
    assert.ok(job.progress > 0.9 && job.progress <= 0.95, String(job.progress));
});

test('packets fly from the coordinator when a job starts and back when it ends, for as long as the flight lasts', () => {
    const synth = synthetic();
    const out = frameAt(synth, T0 + 1000 + 150, { flightMs: 600 }).packets;
    assert.deepEqual(out.filter(p => p.kind === 'dispatch').map(p => p.workerId).sort(), ['a', 'b']);
    assert.equal(out[0].progress, 0.25);
    const back = frameAt(synth, T0 + 3000 + 300, { flightMs: 600 }).packets.find(p => p.kind === 'result');
    assert.equal(back.workerId, 'a'); assert.equal(back.reward, 0.25); assert.equal(back.progress, 0.5);
    assert.equal(frameAt(synth, T0 + 1000 + 700, { flightMs: 600 }).packets.length, 0);
    assert.equal(frameAt(synth, T0 + 4000 + 100, { flightMs: 600 }).packets.find(p => p.kind === 'failed').workerId, 'a');
});

test('marks appear only shortly after they happen, and an unavailable worker shows as offline meanwhile', () => {
    const synth = synthetic();
    assert.equal(frameAt(synth, T0 + 6500).marks.length, 1);
    assert.equal(frameAt(synth, T0 + 20000).marks.length, 0);
    assert.equal(worker(frameAt(synth, T0 + 6500), 'b').state, 'busy', 'a job in progress wins over a mark');
    assert.equal(worker(frameAt(synthetic({ jobs: [] }), T0 + 6500), 'b').state, 'offline');
    assert.equal(worker(frameAt(synthetic({ jobs: [] }), T0 + 6500 + 5000), 'b').state, 'idle', 'the offline flag does not stay on forever');
});

test('a worker that has started but is not ready yet shows as loading the model, until it is ready or has work', () => {
    const marks = [{ atMs: T0 + 100, type: 'worker_start', workerId: 'a', generation: null }, { atMs: T0 + 600, type: 'model_loaded', workerId: 'a', generation: null }, { atMs: T0 + 800, type: 'executor_ready', workerId: 'a', generation: null },
        { atMs: T0 + 300, type: 'worker_start', workerId: 'b', generation: null }];
    const synth = synthetic({ marks, jobs: [] });
    assert.equal(worker(frameAt(synth, T0 + 50), 'a').state, 'idle', 'not started yet');
    assert.equal(worker(frameAt(synth, T0 + 400), 'a').state, 'starting');
    assert.equal(worker(frameAt(synth, T0 + 900), 'a').state, 'idle', 'ready, waiting for work');
    assert.equal(worker(frameAt(synth, T0 + 5000), 'b').state, 'starting', 'b never became ready');
    assert.equal(worker(frameAt(synthetic({ marks, jobs: [{ candidateId: 'x', attemptId: 'x.a1', generation: 0, workerId: 'b', startMs: T0 + 400, endMs: T0 + 900, status: 'SUCCEEDED', reward: 0.1 }] }), T0 + 500), 'b').state, 'busy', 'work wins over loading');
});

test('rewards of completed generations accumulate for the chart', () => {
    assert.deepEqual(frameAt(synthetic(), T0 + 5000).rewards, []);
    assert.deepEqual(frameAt(synthetic(), T0 + 11500).rewards, [{ generation: 0, mean: 0.3, best: 0.5 }]);
});

test('bounds cover the whole run, and a running run ends at "now"', () => {
    assert.deepEqual(runBounds(synthetic()), { startMs: T0, endMs: T0 + 13000 });
    assert.deepEqual(runBounds(synthetic({ experiment: { ...synthetic().experiment, completedMs: T0 + 15000 } })), { startMs: T0, endMs: T0 + 15000 });
    const b = runBounds(real);
    assert.ok(b.startMs < b.endMs);
    assert.deepEqual(runBounds({ ...synthetic(), jobs: [], generations: [], experiment: { ...synthetic().experiment, startedMs: null, createdMs: null } }), { startMs: T0 + 13000, endMs: T0 + 13000 });
});

test('the player advances by real time times speed, stops at the end and cannot go before the start', () => {
    const bounds = { startMs: 0, endMs: 10000 };
    assert.deepEqual(advance({ atMs: 0, playing: true, speed: 4 }, 500, bounds), { atMs: 2000, playing: true, speed: 4 });
    assert.deepEqual(advance({ atMs: 9500, playing: true, speed: 4 }, 500, bounds), { atMs: 10000, playing: false, speed: 4 });
    assert.deepEqual(advance({ atMs: 100, playing: false, speed: 1 }, 500, bounds), { atMs: 100, playing: false, speed: 1 });
    assert.equal(advance({ atMs: 100, playing: true, speed: -1 }, 500, bounds).atMs, 0);
});

test('a real finished run replays: both jobs complete, the model is updated and the totals reach the end', () => {
    const { endMs } = runBounds(real);
    const last = frameAt(real, endMs);
    assert.equal(last.totals.committed, 2);
    assert.equal(last.generation.phase, 'finished');
    assert.equal(worker(last, '5070ti').done, 2);
    assert.equal(worker(last, '3060').state, 'unstarted');
    assert.equal(last.rewards.length, 1);
});

test('a streamed update replaces what changed and never goes backwards in time', () => {
    const older = synthetic();
    const newer = synthetic({ nowMs: T0 + 14000, jobs: [...synthetic().jobs.slice(0, -1), { candidateId: 'd0', attemptId: 'd0.a1', generation: 1, workerId: 'a', startMs: T0 + 12500, endMs: T0 + 14000, status: 'SUCCEEDED', reward: 0.4 }] });
    assert.equal(applyDelta(older, newer).jobs.at(-1).status, 'SUCCEEDED');
    assert.equal(applyDelta(newer, older).nowMs, newer.nowMs, 'a late, older message is ignored');
    assert.equal(applyDelta(undefined, newer), newer);
});
