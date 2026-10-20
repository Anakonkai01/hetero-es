import { test } from 'node:test';
import assert from 'node:assert/strict';
import { DEFAULT_V3, withAlphaSchedule, v3ReviewRows } from '../src/lib/v3Settings.ts';

test('the review distinguishes raw prompts and the boxed format reward', () => {
  const rows = Object.fromEntries(
    v3ReviewRows(
      {
        ...DEFAULT_V3,
        promptFormat: 'raw',
        scorer: {
          kind: 'declarative',
          name: 'boxed-number',
          version: 1,
          codeSha256: null,
          config: { answerField: 'answer', formatReward: 0.1 },
        },
      },
      {
        dataset: 'numbers',
        batchSize: 4,
        batchSeed: 11,
        sigma: 0.001,
        sigmaSchedule: 'constant',
        sigmaMinimum: 0.001,
        alpha: 0.001,
        maxNewTokens: 32,
      },
    ),
  );
  assert.equal(rows['Prompt format'], 'raw');
  assert.equal(rows['Format reward'], '0.1');
});

test('a decaying alpha starts with an end value of a tenth of alpha, keeps a chosen one, constant clears it', () => {
  assert.equal(withAlphaSchedule(DEFAULT_V3, 'cosine', 0.0005).alphaMinimum, 0.00005);
  assert.equal(withAlphaSchedule(DEFAULT_V3, 'linear', 0.001).alphaSchedule, 'linear');
  assert.equal(withAlphaSchedule({ ...DEFAULT_V3, alphaMinimum: 0.0002 }, 'cosine', 0.001).alphaMinimum, 0.0002);
  const back = withAlphaSchedule({ ...DEFAULT_V3, alphaSchedule: 'cosine', alphaMinimum: 0.0002 }, 'constant', 0.001);
  assert.deepEqual([back.alphaSchedule, back.alphaMinimum], ['constant', null]);
});

test('the review lists every ES choice, with schedules shown as start → end', () => {
  const rows = Object.fromEntries(
    v3ReviewRows(
      {
        ...DEFAULT_V3,
        alphaSchedule: 'cosine',
        alphaMinimum: 0.0001,
        momentumBeta: 0.875,
        coefficientRule: 'centered-rank@1',
        candidateSeedNamespace: 'baseline-5070',
      },
      {
        dataset: 'GSM8K',
        batchSize: 32,
        batchSeed: 11,
        sigma: 0.001,
        sigmaSchedule: 'cosine',
        sigmaMinimum: 0.00025,
        alpha: 0.0005,
        maxNewTokens: 512,
      },
    ),
  );
  assert.equal(rows['Sigma'], '0.001 → 0.00025 (cosine)');
  assert.equal(rows['Alpha'], '0.0005 → 0.0001 (cosine)');
  assert.equal(rows['Coefficient rule'], 'centered-rank@1');
  assert.equal(rows['Momentum'], 'β 0.875 · 4');
  assert.equal(rows['Batch'], '32 · seed 11');
  assert.equal(rows['Prompts per generate() call'], '16');
  assert.equal(rows['Declarative scorer'], 'exact-string@1');
  assert.equal(rows['Batch sampler'], 'sha256-python-random-sample-v1');
  assert.equal(rows['Candidate seed group'], 'baseline-5070');
  const constant = Object.fromEntries(
    v3ReviewRows(DEFAULT_V3, {
      dataset: 'd',
      batchSize: 1,
      batchSeed: 0,
      sigma: 0.002,
      sigmaSchedule: 'constant',
      sigmaMinimum: 0.002,
      alpha: 0.001,
      maxNewTokens: 8,
    }),
  );
  assert.deepEqual([constant['Sigma'], constant['Alpha'], constant['Momentum']], ['0.002', '0.001', '—']);
});
