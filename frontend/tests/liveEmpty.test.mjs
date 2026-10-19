import { test } from 'node:test';
import assert from 'node:assert/strict';
import { emptyLiveText } from '../src/lib/liveEmpty.ts';

test('a run that is starting says the GPUs are loading the model, not that nothing happened', () => {
  for (const status of ['QUEUED', 'STARTING', 'RUNNING', 'DRAINING']) {
    const text = emptyLiveText(status);
    assert.equal(text.title, 'Starting up', status);
    assert.match(text.message, /loading the model/);
  }
});

test('a run that ended before any candidate ran says so', () => {
  for (const status of ['COMPLETED', 'CANCELLED', 'FAILED']) {
    const text = emptyLiveText(status);
    assert.equal(text.title, 'Nothing has run yet', status);
    assert.equal(text.message, 'This experiment ended before any candidate ran.');
  }
});

test('an unknown or missing status is treated as not started yet', () => {
  assert.equal(emptyLiveText('').title, 'Starting up');
  assert.equal(emptyLiveText('SOMETHING_NEW').title, 'Starting up');
});
