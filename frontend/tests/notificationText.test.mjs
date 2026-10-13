import { test } from 'node:test';
import assert from 'node:assert/strict';
import { describeNotification, newUnread, relativeTime } from '../src/lib/notificationText.ts';
import { fillTemplate } from '../src/lib/eventText.ts';

const say = item => { const d = describeNotification(item); return [fillTemplate(d.title, d.params), d.tone]; };

test('every kind the backend creates has a sentence with its parameters filled in', () => {
    assert.deepEqual(say({ kind: 'account.request', params: { username: 'an', displayName: 'An Nguyen' } }), ['New account request: An Nguyen (@an)', 'warn']);
    assert.deepEqual(say({ kind: 'device.request', params: { name: 'Quang 3060' } }), ['A GPU computer is waiting for approval: Quang 3060', 'warn']);
    assert.deepEqual(say({ kind: 'account.approved', params: {} }), ['Your account was approved', 'ok']);
    assert.deepEqual(say({ kind: 'account.rejected', params: {} }), ['Your account request was declined', 'err']);
    assert.deepEqual(say({ kind: 'account.suspended', params: {} }), ['Your account was suspended', 'err']);
    assert.deepEqual(say({ kind: 'run.completed', params: { name: 'Overnight' } }), ['Experiment finished: Overnight', 'ok']);
    assert.deepEqual(say({ kind: 'run.failed', params: { name: 'Overnight' } }), ['Experiment failed: Overnight', 'err']);
    assert.deepEqual(say({ kind: 'run.cancelled', params: { name: 'Overnight' } }), ['Experiment cancelled: Overnight', 'warn']);
});

test('a missing parameter or an unknown kind never breaks the list', () => {
    assert.equal(say({ kind: 'run.completed', params: {} })[0], 'Experiment finished:');
    assert.deepEqual(say({ kind: 'something.new', params: {} }), ['Something new', 'info']);
    assert.doesNotThrow(() => describeNotification({ kind: 'run.completed' }));
});

test('only unread notifications that were not there before count as new, and the first load announces nothing', () => {
    const items = [{ id: '3', read: false }, { id: '2', read: false }, { id: '1', read: true }];
    assert.deepEqual(newUnread(undefined, items), [], 'first load');
    assert.deepEqual(newUnread(new Set(['1', '2']), items).map(i => i.id), ['3']);
    assert.deepEqual(newUnread(new Set(['1', '2', '3']), items), []);
    assert.deepEqual(newUnread(new Set(), [{ id: '9', read: true }]), [], 'already read ones are not announced');
});

test('relative time reads naturally in both languages', () => {
    const now = Date.parse('2026-10-13T12:00:00Z');
    assert.equal(relativeTime('2026-10-13T11:59:50Z', now, 'en'), 'just now');
    assert.equal(relativeTime('2026-10-13T11:55:00Z', now, 'en'), '5 min ago');
    assert.equal(relativeTime('2026-10-13T09:00:00Z', now, 'en'), '3 h ago');
    assert.equal(relativeTime('2026-10-11T12:00:00Z', now, 'en'), '2 d ago');
    assert.equal(relativeTime('2026-10-13T11:55:00Z', now, 'vi'), '5 phút trước');
    assert.equal(relativeTime('2026-10-13T11:59:50Z', now, 'vi'), 'vừa xong');
    assert.equal(relativeTime('garbage', now, 'en'), '');
    assert.equal(relativeTime('2026-10-13T12:05:00Z', now, 'en'), 'just now', 'a clock a little ahead is not "in the future"');
});
