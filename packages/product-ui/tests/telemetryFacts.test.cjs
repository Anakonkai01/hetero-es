const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const scope = { exports: {} };
vm.runInNewContext(
  ts.transpileModule(fs.readFileSync('packages/product-ui/src/telemetryFacts.ts', 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText,
  scope,
);
const { cpuTemperature, metricUnavailableLabel } = scope.exports;
test('CPU temperatures recognize Intel/AMD package sensors without relabeling ACPI zones', () => {
  const sensor = (group, label, value) => ({ group, label, value, kind: 'temperature', unit: '°C' });
  assert.equal(cpuTemperature([sensor('k10temp', 'Tctl', 70), sensor('k10temp', 'Tdie', 60)]), 60);
  assert.equal(cpuTemperature([sensor('coretemp', 'Package id 0', 0)]), 0);
  assert.equal(cpuTemperature([sensor('ACPI thermal zone', 'TZ00', 32)]), undefined);
  assert.equal(cpuTemperature([]), undefined);
});
test('legacy absence is unknown, explicit unavailable reasons remain distinct', () => {
  assert.equal(metricUnavailableLabel(undefined, 'cpuPercent'), 'No data yet');
  assert.equal(metricUnavailableLabel({ cpuPercent: { status: 'warming_up' } }, 'cpuPercent'), 'Measuring…');
  assert.equal(metricUnavailableLabel({ cpuPowerW: { status: 'unsupported' } }, 'cpuPowerW'), 'Not supported');
  assert.equal(
    metricUnavailableLabel({ cpuPercent: { status: 'permission_denied' } }, 'cpuPercent'),
    'Permission required',
  );
  assert.equal(metricUnavailableLabel({ cpuPercent: { status: 'error' } }, 'cpuPercent'), 'Measurement failed');
});
