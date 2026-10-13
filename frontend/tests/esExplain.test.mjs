import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { standardize, noiseCloud, explainFromTimeline, commandRank } from '../src/lib/esExplain.ts';

const demo = JSON.parse(fs.readFileSync(new URL('../static/demo/run.json', import.meta.url), 'utf8'));

test('standardised rewards have mean 0 and spread 1, and keep the order of the rewards', () => {
    const z = standardize([0.1, 0.2, 0.3, 0.4]);
    assert.ok(Math.abs(z.reduce((a, b) => a + b, 0)) < 1e-9);
    assert.ok(Math.abs(Math.sqrt(z.reduce((a, b) => a + b * b, 0) / z.length) - 1) < 1e-9);
    assert.ok(z[0] < z[1] && z[1] < z[2] && z[2] < z[3]);
});

test('when every candidate scored the same nothing is learned: all weights are zero, never NaN', () => {
    assert.deepEqual(standardize([0.25, 0.25, 0.25]), [0, 0, 0]);
    assert.deepEqual(standardize([]), []);
    assert.deepEqual(standardize([0.5]), [0]);
});

test('the noise picture is the same every time for the same seed and stays inside its circle', () => {
    const a = noiseCloud(12, 7, 100), b = noiseCloud(12, 7, 100), c = noiseCloud(12, 8, 100);
    assert.deepEqual(a, b);
    assert.notDeepEqual(a, c);
    assert.equal(a.length, 12);
    for (const p of a) assert.ok(Math.hypot(p.x, p.y) <= 100 + 1e-9);
    assert.deepEqual(noiseCloud(0, 1, 100), []);
});

test('the real demo run provides the numbers the explanation shows', () => {
    const e = explainFromTimeline(demo);
    assert.equal(e.candidates.length, 12);
    assert.ok(e.candidates.every(c => typeof c.reward === 'number' && c.worker));
    assert.equal(e.candidates.map(c => c.worker).filter((w, i, all) => all.indexOf(w) === i).length, 3, 'three different GPUs took part');
    assert.equal(e.weights.length, 12);
    assert.ok(Math.abs(e.weights.reduce((a, b) => a + b, 0)) < 1e-9);
    assert.equal(e.generations.length, 3);
    assert.ok(e.generations.every(g => g.mean > 0 && g.best >= g.mean));
    assert.equal(e.totalCandidates, 36);
});

test('an empty or unfinished timeline gives an explanation with no numbers instead of failing', () => {
    const empty = explainFromTimeline({ experiment: {}, workers: [], generations: [], jobs: [], marks: [], nowMs: 0 });
    assert.deepEqual([empty.candidates, empty.weights, empty.generations, empty.totalCandidates], [[], [], [], 0]);
});

test('the command palette ranks exact and prefix matches first, ignores accents and case, and drops non-matches', () => {
    const items = [{ id: 'a', label: 'Create experiment' }, { id: 'b', label: 'Experiments' }, { id: 'c', label: 'Thí nghiệm' }, { id: 'd', label: 'Workers' }, { id: 'e', label: 'My experiment notes' }];
    assert.deepEqual(commandRank(items, 'exp').map(i => i.id), ['b', 'a', 'e']);
    assert.deepEqual(commandRank(items, 'thi ng').map(i => i.id), ['c'], 'accents are ignored');
    assert.deepEqual(commandRank(items, 'WORK').map(i => i.id), ['d']);
    assert.deepEqual(commandRank(items, '').map(i => i.id), ['a', 'b', 'c', 'd', 'e'], 'no query keeps the order');
    assert.deepEqual(commandRank(items, 'zzz'), []);
    assert.deepEqual(commandRank(items, 'cr ex').map(i => i.id), ['a'], 'every word must match somewhere');
});
