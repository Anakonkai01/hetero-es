import { test } from 'node:test';
import assert from 'node:assert/strict';
import { memberView } from '../src/lib/membership.ts';

const join = (workerId) => ({ workerId, action: 'JOIN' });
const leave = (workerId) => ({ workerId, action: 'LEAVE' });

test('before any request the members are the selected workers', () => {
  assert.deepEqual(memberView({ workerIds: ['a', 'b'] }), [
    { workerId: 'a', state: 'member' },
    { workerId: 'b', state: 'member' },
  ]);
});

test('a requested join is shown as joining until the coordinator applies it', () => {
  const requested = { workerIds: ['a'], membershipRequests: [join('late')] };
  assert.deepEqual(memberView(requested), [
    { workerId: 'a', state: 'member' },
    { workerId: 'late', state: 'joining' },
  ]);
  const applied = { ...requested, membership: { members: ['a', 'late'], left: [] } };
  assert.deepEqual(memberView(applied), [
    { workerId: 'a', state: 'member' },
    { workerId: 'late', state: 'member' },
  ]);
});

test('a requested leave is shown as leaving, then as left', () => {
  const requested = { workerIds: ['a', 'b'], membershipRequests: [leave('b')] };
  assert.deepEqual(memberView(requested), [
    { workerId: 'a', state: 'member' },
    { workerId: 'b', state: 'leaving' },
  ]);
  const applied = { ...requested, membership: { members: ['a'], left: ['b'] } };
  assert.deepEqual(memberView(applied), [
    { workerId: 'a', state: 'member' },
    { workerId: 'b', state: 'left' },
  ]);
});
