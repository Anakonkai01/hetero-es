import { test } from 'node:test';
import assert from 'node:assert/strict';
import { watchdogSettings } from '../src/lib/watchdog.ts';

test('empty fields keep the lab defaults', () => {
  assert.deepEqual(watchdogSettings('', ' '), {});
});

test('values within the lab limits are sent as numbers', () => {
  assert.deepEqual(watchdogSettings('3600', '300'), { hardCapSeconds: 3600, stallSeconds: 300 });
  assert.deepEqual(watchdogSettings('60', ''), { hardCapSeconds: 60 });
  assert.deepEqual(watchdogSettings('', '604800'), { stallSeconds: 604800 });
});

test('values outside the limits are refused with their own sentence', () => {
  assert.deepEqual(watchdogSettings('59', ''), { error: 'The generation hard cap is 60 to 604800 seconds.' });
  assert.deepEqual(watchdogSettings('604801', ''), { error: 'The generation hard cap is 60 to 604800 seconds.' });
  assert.deepEqual(watchdogSettings('abc', ''), { error: 'The generation hard cap is 60 to 604800 seconds.' });
  assert.deepEqual(watchdogSettings('', '29'), { error: 'The stall time is 30 to 604800 seconds.' });
  assert.deepEqual(watchdogSettings('', 'Infinity'), { error: 'The stall time is 30 to 604800 seconds.' });
});

test('the stall time must be shorter than the hard cap', () => {
  assert.deepEqual(watchdogSettings('300', '300'), {
    error: 'The stall time must be shorter than the generation hard cap.',
  });
  assert.deepEqual(watchdogSettings('300', '299'), { hardCapSeconds: 300, stallSeconds: 299 });
});
