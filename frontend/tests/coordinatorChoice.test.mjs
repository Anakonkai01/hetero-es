import { test } from 'node:test';
import assert from 'node:assert/strict';
import { suggestCoordinator } from '../src/lib/coordinatorChoice.ts';

const cpu = { deviceId: 'cpu', gpu: false, updateSecondsPerSeed: null };
const fast = { deviceId: 'rtx5070ti', gpu: true, updateSecondsPerSeed: 0.09 };
const slow = { deviceId: 'rtx3060', gpu: true, updateSecondsPerSeed: 0.25 };

test('a GPU coordinator is preferred to the lab default when that default is CPU-only', () => {
  assert.equal(suggestCoordinator([cpu, fast, slow], 'cpu', false), 'rtx5070ti');
  assert.equal(suggestCoordinator([cpu, fast], null, false), 'rtx5070ti');
});

test('a lab default that is a GPU coordinator is kept', () => {
  assert.equal(suggestCoordinator([cpu, fast, slow], 'rtx3060', false), 'rtx3060');
  assert.equal(suggestCoordinator([cpu, fast, slow], 'rtx5070ti', true), 'rtx5070ti');
});

test('other decoders get the fastest GPU, which may also work', () => {
  assert.equal(suggestCoordinator([slow, fast], null, false), 'rtx5070ti');
});

test('a strict run can favour the fastest coordinator', () => {
  assert.equal(suggestCoordinator([fast, slow, cpu], null, true), 'rtx5070ti');
  const unmeasured = { deviceId: 'new-gpu', gpu: true, updateSecondsPerSeed: null };
  assert.equal(suggestCoordinator([fast, unmeasured], null, true), 'rtx5070ti');
  assert.equal(suggestCoordinator([unmeasured, fast], null, false), 'rtx5070ti');
});

test('without a GPU only other decoders can use the lab default', () => {
  assert.equal(suggestCoordinator([cpu], 'cpu', true), '');
  assert.equal(suggestCoordinator([cpu], 'cpu', false), 'cpu');
  assert.equal(suggestCoordinator([cpu], 'gone', false), '');
  assert.equal(suggestCoordinator([], null, false), '');
});
