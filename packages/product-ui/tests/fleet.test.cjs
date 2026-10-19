const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const code = ts.transpileModule(fs.readFileSync('packages/product-ui/src/fleet.ts', 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
const scope = { exports: {} };
vm.runInNewContext(code, scope);
const { fleetResources } = scope.exports;
function component(id, kind, w) {
  return {
    id,
    kind,
    powerW: w,
    includedInSubtotal: kind !== 'wall' && kind !== 'cpu-domain',
    energy: { sampledSeconds: 10, todayWh: 1 },
  };
}
function observation(at, components) {
  return { sampledAt: at, power: { hostId: 'same-host', components } };
}
test('CPU host identity and GPU UUID deduplicate aliases, nested domains and wall are excluded', () => {
  const shared = component('cpu:host:package', 'cpu-package', 40),
    gpu = component('gpu:uuid', 'gpu', 10),
    core = component('cpu:host:core', 'cpu-domain', 30),
    wall = component('wall:host', 'wall', 80);
  const result = fleetResources(
    [observation(99, [shared, gpu, core, wall]), observation(100, [{ ...shared, powerW: 45 }, gpu, core, wall])],
    100,
  );
  assert.equal(result.hostCount, 1);
  assert.equal(result.componentW, 55);
  assert.equal(result.wholeW, 80);
  assert.equal(result.energyComponents.length, 2);
});
test('stale and missing observations are not zero watts; recorded energy remains available', () => {
  const result = fleetResources([observation(1, [component('gpu:uuid', 'gpu', 10)])], 100);
  assert.equal(result.componentW, null);
  assert.equal(result.cpuW, null);
  assert.equal(result.energyComponents.length, 1);
});
