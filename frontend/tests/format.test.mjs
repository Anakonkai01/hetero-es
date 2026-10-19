import { test } from 'node:test';
import assert from 'node:assert/strict';
import { formatDateTime, formatFullDateTime } from '../src/lib/format.ts';

const iso = '2026-10-12T10:55:07.000Z'; // 17:55:07 in GMT+7

test('dates follow the language: month names for English, day/month for Vietnamese, always GMT+7', () => {
  assert.equal(formatDateTime(iso, 'en'), 'Oct 12 17:55');
  assert.equal(formatDateTime(iso, 'vi'), '12/10 17:55');
  assert.equal(formatFullDateTime(iso, 'en'), 'Oct 12 17:55:07');
  assert.equal(formatFullDateTime(iso, 'vi'), '12/10 17:55:07');
  assert.equal(formatDateTime(undefined, 'vi'), '—');
});

test("a day boundary uses the GMT+7 calendar, not the viewer's", () => {
  assert.equal(formatDateTime('2026-10-12T20:30:00.000Z', 'vi'), '13/10 03:30');
});
