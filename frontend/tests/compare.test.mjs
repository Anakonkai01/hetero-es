import { test } from 'node:test';
import assert from 'node:assert/strict';
import { compareRuns, configDifferences, runDurationSeconds } from '../src/lib/compare.ts';
import { generationsCsv, summaryMarkdown, csvCell } from '../src/lib/exportRun.ts';

const experiment = (id, over = {}) => ({ experimentId: id, name: `Run ${id}`, status: 'COMPLETED', task: 'arith16', modelName: 'Qwen', schedulerPolicy: 'greedy', syncMode: 'synchronous', candidatesPerGeneration: 8, maxGenerations: 3, alpha: 0.001, sigma: 0.001, decodeEngine: 'hf_generate', workerIds: ['a', 'b'], createdAt: '2026-10-10T08:00:00+00:00', startedAt: '2026-10-10T08:00:10+00:00', completedAt: '2026-10-10T08:01:40+00:00', configHash: 'h' + id, ...over });
const generation = (index, mean, best, over = {}) => ({ generationId: `r.g${index}`, status: 'COMPLETED', candidateCount: 8, committedCandidateCount: 8, rewardMean: mean, rewardBest: best, startedAt: '2026-10-10T08:00:10+00:00', completedAt: '2026-10-10T08:00:30+00:00', ...over });

test('each run becomes a series of per-generation points, and generations without a reward are left out', () => {
    const result = compareRuns([
        { experiment: experiment('1'), generations: [generation(0, 0.2, 0.3), generation(1, 0.25, 0.35), generation(2, undefined, undefined, { status: 'RUNNING' })] },
        { experiment: experiment('2'), generations: [generation(0, 0.1, 0.2)] },
    ]);
    assert.deepEqual(result.series.map(s => s.id), ['1', '2']);
    assert.deepEqual(result.series[0].points, [{ generation: 0, mean: 0.2, best: 0.3 }, { generation: 1, mean: 0.25, best: 0.35 }]);
    assert.equal(result.maxGeneration, 1);
    assert.equal(result.maxReward, 0.35);
});

test('the summary row has the numbers a reader compares: best, last mean, duration, GPUs', () => {
    const [row] = compareRuns([{ experiment: experiment('1'), generations: [generation(0, 0.2, 0.3), generation(1, 0.25, 0.35)] }]).rows;
    assert.equal(row.bestReward, 0.35);
    assert.equal(row.lastMean, 0.25);
    assert.equal(row.durationSeconds, 90);
    assert.deepEqual(row.workers, ['a', 'b']);
    assert.equal(row.completedGenerations, 2);
    assert.equal(row.status, 'COMPLETED');
});

test('runs with no results yet still produce a row with empty values', () => {
    const [row] = compareRuns([{ experiment: experiment('1', { startedAt: undefined, completedAt: undefined, status: 'QUEUED' }), generations: [] }]).rows;
    assert.equal(row.bestReward, null); assert.equal(row.lastMean, null); assert.equal(row.durationSeconds, null);
});

test('only settings that differ between the runs are listed, with each run\'s value', () => {
    const diffs = configDifferences([experiment('1'), experiment('2', { candidatesPerGeneration: 16, workerIds: ['a'], alpha: 0.002 }), experiment('3', { candidatesPerGeneration: 16 })]);
    assert.deepEqual(diffs.map(d => d.key), ['alpha', 'candidatesPerGeneration', 'workerIds']);
    assert.deepEqual(diffs.find(d => d.key === 'candidatesPerGeneration').values, ['8', '16', '16']);
    assert.deepEqual(diffs.find(d => d.key === 'workerIds').values, ['a, b', 'a', 'a, b']);
    assert.deepEqual(configDifferences([experiment('1'), experiment('2')]), [], 'identical settings: nothing to show');
    assert.deepEqual(configDifferences([experiment('1')]), []);
});

test('a duration needs both ends and never goes negative', () => {
    assert.equal(runDurationSeconds(experiment('1')), 90);
    assert.equal(runDurationSeconds(experiment('1', { completedAt: undefined })), null);
    assert.equal(runDurationSeconds(experiment('1', { completedAt: '2026-10-10T07:00:00+00:00' })), null);
});

test('CSV cells are quoted when they need to be and formulas are neutralised', () => {
    assert.equal(csvCell('plain'), 'plain');
    assert.equal(csvCell('a,b'), '"a,b"');
    assert.equal(csvCell('say "hi"'), '"say ""hi"""');
    assert.equal(csvCell('two\nlines'), '"two\nlines"');
    assert.equal(csvCell('=SUM(A1)'), "'=SUM(A1)");
    assert.equal(csvCell('-5'), '-5', 'a plain negative number is not a formula');
    assert.equal(csvCell(null), ''); assert.equal(csvCell(undefined), ''); assert.equal(csvCell(0.25), '0.25');
});

test('the generations CSV has one header and one row per generation, numbered from 1', () => {
    const csv = generationsCsv(experiment('1'), [generation(0, 0.2, 0.3), generation(1, 0.25, 0.35)]);
    const lines = csv.trim().split('\n');
    assert.equal(lines[0], 'generation,status,candidates,committed,reward_mean,reward_best,started,completed');
    assert.equal(lines.length, 3);
    assert.ok(lines[1].startsWith('1,COMPLETED,8,8,0.2,0.3,'));
    assert.ok(csv.endsWith('\n'));
});

test('the Markdown summary states the setup and the results, and says what it does not show', () => {
    const md = summaryMarkdown(experiment('1'), [generation(0, 0.2, 0.3), generation(1, 0.25, 0.35)]);
    assert.match(md, /^# Run 1/);
    assert.match(md, /\| Workload \| arith16 \|/);
    assert.match(md, /\| 2 \| 0\.2500 \| 0\.3500 \|/);
    assert.match(md, /Reward is a task score/);
    assert.ok(!md.includes('undefined') && !md.includes('NaN'));
    assert.ok(summaryMarkdown(experiment('1', { startedAt: undefined }), []).includes('No generation has a reward yet'));
});
