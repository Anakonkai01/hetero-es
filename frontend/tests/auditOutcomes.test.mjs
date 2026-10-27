import { test } from 'node:test';
import assert from 'node:assert/strict';
import { auditOutcomeLines } from '../src/lib/auditOutcomes.ts';

const base = {
  selected: 0,
  matched: 0,
  mismatched: 0,
  pending: 0,
  timedOut: 0,
  skipped: 0,
  unknown: 0,
  enabled: true,
  rate: 0.05,
  known: true,
  policy: 'historical',
  drainReasons: {},
  strictStop: null,
  restoreFaults: [],
};
const fill = ({ template, params }) => template.replace(/\{(\w+)\}/g, (_w, name) => String(params[name]));
const text = (outcomes, names) => auditOutcomeLines(outcomes, names).map((line) => line.segments.map(fill).join(' · '));
const tones = (outcomes) => auditOutcomeLines(outcomes).map((line) => line.tone);

test('zero coverage says disabled, never checked', () => {
  assert.deepEqual(text({ ...base, enabled: false, rate: 0 }), ['Audits are disabled (rate 0)']);
});

test('zero selected at a positive rate is not evidence that results were checked', () => {
  assert.deepEqual(text(base), [
    'Audit outcomes: 0 chosen',
    'No candidate has been chosen for audit yet; this is not evidence that results were checked.',
  ]);
  assert.deepEqual(tones(base), ['warn', 'warn']);
});

test('every outcome is named, counted once and only when present', () => {
  const shown = { ...base, selected: 9, matched: 4, mismatched: 1, pending: 1, timedOut: 1, skipped: 1, unknown: 1 };
  assert.deepEqual(
    text(shown)[0],
    'Audit outcomes: 9 chosen · 4 matched · 1 mismatched · 1 pending · 1 timed out · 1 skipped · 1 unknown',
  );
  assert.equal(tones(shown)[0], 'err');
  assert.equal(text({ ...base, selected: 4, matched: 4 })[0], 'Audit outcomes: 4 chosen · 4 matched');
  assert.equal(tones({ ...base, selected: 4, matched: 4 })[0], 'info');
  assert.equal(tones({ ...base, selected: 4, timedOut: 4 })[0], 'warn');
  assert.equal(text({ ...base, selected: 4, skipped: 4 })[0], 'Audit outcomes: 4 chosen · 4 skipped');
});

test('missing evidence and the strict policy are explained', () => {
  const lines = text({ ...base, selected: 2, unknown: 2, known: false, policy: 'strict-stop' });
  assert.ok(lines.includes('Some audit evidence is missing or from an older run; unknown is not a match.'));
  assert.ok(lines.includes('Strict decoder: the first audit mismatch stops the run before the next update.'));
});

test('a strict stop names the candidate and both workers by their display names', () => {
  const stop = { candidateId: 'r/g0/c3', generation: 0, originalWorker: 'w1', auditorWorker: 'w2' };
  const lines = text(
    { ...base, selected: 1, mismatched: 1, policy: 'strict-stop', strictStop: stop },
    { w1: '5070 Ti' },
  );
  assert.ok(
    lines.includes(
      'Strict audit mismatch on r/g0/c3 (generation 1): 5070 Ti and w2 produced different text. The run stopped before the next update and needs operator review.',
    ),
  );
  assert.equal(auditOutcomeLines({ ...base, strictStop: stop }).at(-1).tone, 'err');
});

test('restore faults list their workers', () => {
  assert.ok(
    text({ ...base, selected: 1, matched: 1, restoreFaults: ['w1'] }, { w1: '3060' }).includes(
      'Exact restore failed on: 3060',
    ),
  );
});
