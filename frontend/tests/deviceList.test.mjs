import { test } from 'node:test';
import assert from 'node:assert/strict';
import { visibleDevices, canRemoveDevice, hiddenCount, deviceErrorKey } from '../src/lib/deviceList.ts';

const d = (workerId, approvalStatus) => ({ deviceId: 'id-' + workerId, workerId, approvalStatus });
const all = [d('a', 'APPROVED'), d('b', 'REVOKED'), d('c', 'PENDING'), d('e', 'REVOKED'), d('f', 'QUARANTINED')];

test('revoked devices are hidden by default and shown on request, order kept', () => {
  assert.deepEqual(
    visibleDevices(all, false).map((x) => x.workerId),
    ['a', 'c', 'f'],
  );
  assert.deepEqual(
    visibleDevices(all, true).map((x) => x.workerId),
    ['a', 'b', 'c', 'e', 'f'],
  );
  assert.equal(hiddenCount(all), 2);
  assert.equal(hiddenCount([]), 0);
});

test('only revoked and pending devices can be removed, never an approved or quarantined one', () => {
  assert.equal(canRemoveDevice(d('x', 'REVOKED')), true);
  assert.equal(canRemoveDevice(d('x', 'PENDING')), true);
  assert.equal(canRemoveDevice(d('x', 'APPROVED')), false);
  assert.equal(canRemoveDevice(d('x', 'QUARANTINED')), false);
});

test("the lab's English error text maps to an explanation that says what to do, anything else is left alone", () => {
  assert.match(deviceErrorKey('Owner must belong to target workspace'), /Add them to the workspace first/);
  assert.match(deviceErrorKey('Revoke the device before removing it'), /Revoke this device first/);
  assert.match(deviceErrorKey('Device is reserved'), /running experiment/);
  assert.match(deviceErrorKey('Re-enroll with a new device alias after revocation'), /Pair the computer again/);
  assert.equal(deviceErrorKey('something else'), null);
  assert.equal(deviceErrorKey('constructor'), null, 'inherited object keys are not messages');
  assert.equal(deviceErrorKey(undefined), null);
});
