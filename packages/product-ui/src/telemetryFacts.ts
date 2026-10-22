type Sensor = { group: string; label: string; kind: string; unit: string; value: number };
export type Availability = Record<
  string,
  { status: 'warming_up' | 'unsupported' | 'permission_denied' | 'error' | 'unavailable' }
>;

export function cpuTemperature(sensors: Sensor[] | undefined): number | undefined {
  const temperatures = (sensors ?? []).filter(
    (sensor) => sensor.kind === 'temperature' && Number.isFinite(sensor.value),
  );
  for (const match of [/tdie/i, /package/i, /tctl/i, /cpu/i]) {
    const known = temperatures.filter(
      (sensor) => /coretemp|k10temp|zenpower|cpu/i.test(sensor.group) && match.test(sensor.label),
    );
    if (known.length) return Math.max(...known.map((sensor) => sensor.value));
  }
  return undefined;
}

export function metricUnavailableLabel(availability: Availability | undefined, key: string): string {
  const status = availability?.[key]?.status;
  if (status === 'warming_up') return 'Measuring…';
  if (status === 'unsupported') return 'Not supported';
  if (status === 'permission_denied') return 'Permission required';
  if (status === 'error') return 'Measurement failed';
  return 'No data yet';
}
