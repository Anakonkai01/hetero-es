import { test } from 'node:test';
import assert from 'node:assert/strict';
import { stationView, gauges } from '../src/station.ts';

const base = {
  signedIn: true,
  device: { approvalStatus: 'APPROVED' },
  agent: { enabled: false, drained: true, error: undefined, assignments: [] },
  connection: 'ONLINE',
  telemetry: null,
  nowSeconds: 1000,
};
const view = (over) => stationView({ ...base, ...over, agent: over?.agent === undefined ? base.agent : over.agent });

test('an approved, signed-in station that is OFF offers to start contributing', () => {
  const v = view();
  assert.equal(v.mode, 'off');
  assert.equal(v.toggle.action, 'enable');
  assert.equal(v.toggle.disabled, false);
  assert.equal(v.headline, 'Contribution is OFF');
});

test('ON with no work is ready; ON with a live worker is working and says for which assignment', () => {
  const ready = view({ agent: { enabled: true, drained: false, assignments: [] } });
  assert.equal(ready.mode, 'ready');
  assert.equal(ready.toggle.action, 'stop');
  const working = view({
    agent: {
      enabled: true,
      drained: false,
      assignments: [{ assignmentId: 'abc', epoch: 3, workerAlive: true, coordinatorAlive: false, ready: true }],
    },
  });
  assert.equal(working.mode, 'working');
  assert.deepEqual(working.assignments, [{ id: 'abc', epoch: 3, ready: true }]);
  assert.equal(working.toggle.action, 'stop');
});

test('stopping shows draining and cannot be pressed again; an unknown process state holds the toggle', () => {
  const draining = view({
    agent: {
      enabled: false,
      drained: false,
      assignments: [{ assignmentId: 'a', workerAlive: true, coordinatorAlive: true }],
    },
  });
  assert.equal(draining.mode, 'draining');
  assert.equal(draining.toggle.disabled, true);
  const unknown = view({
    agent: {
      enabled: true,
      drained: false,
      assignments: [{ assignmentId: 'a', workerAlive: null, coordinatorAlive: null }],
    },
  });
  assert.equal(unknown.mode, 'unknown');
  assert.equal(
    view({ agent: { enabled: false, drained: false, error: 'AGENT_UNAVAILABLE', assignments: [] } }).mode,
    'unknown',
  );
});

test('starting requires approval and an agent, while paired contribution does not require sign-in', () => {
  const waiting = view({ device: { approvalStatus: 'PENDING' } });
  assert.equal(waiting.toggle.disabled, true);
  assert.equal(waiting.blocker, 'approval');
  const signedOut = view({ signedIn: false });
  assert.equal(signedOut.toggle.disabled, false);
  assert.equal(signedOut.blocker, null);
  const noAgent = view({ agent: null });
  assert.equal(noAgent.mode, 'off');
  assert.equal(noAgent.blocker, 'agent');
  assert.equal(
    view({ signedIn: false, agent: { enabled: true, drained: false, assignments: [] } }).toggle.disabled,
    false,
    'stopping never needs a sign-in',
  );
});

test('gauges come from fresh measurements only and never invent a number', () => {
  const fresh = {
    sampledAt: 990,
    gpu: { utilizationPercent: 62.4, vramUsedMb: 8192, vramTotalMb: 12288, temperatureC: 61 },
  };
  const [util, vram, temp] = gauges(fresh, 1000);
  assert.deepEqual([util.key, util.percent, util.text], ['gpu', 62, '62 %']);
  assert.deepEqual([vram.key, vram.percent, vram.text], ['vram', 67, '8.0 / 12.0 GiB']);
  assert.deepEqual([temp.key, temp.percent, temp.text], ['temp', 61, '61 °C']);
  for (const gauge of gauges({ sampledAt: 100, gpu: fresh.gpu }, 1000))
    assert.equal(gauge.percent, null, 'a stale sample is shown as unknown');
  for (const gauge of gauges(null, 1000)) {
    assert.equal(gauge.percent, null);
    assert.equal(gauge.text, '—');
  }
  assert.equal(gauges({ sampledAt: 999, gpu: { vramUsedMb: 1, vramTotalMb: 0 } }, 1000)[1].percent, null);
  assert.equal(
    gauges({ receivedAt: 995, sampledAt: 1, gpu: { temperatureC: 200 } }, 1000)[2].percent,
    100,
    'a bar never overflows',
  );
});
