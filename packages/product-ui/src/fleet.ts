import type { ResourceObservation, PowerComponent } from './telemetry';
/** Hardware identity prevents aliases counting the same CPU package/GPU twice. */
export function fleetResources(observations: ResourceObservation[], now: number) {
  const components = new Map<string, PowerComponent>();
  const fresh = new Map<string, PowerComponent>();
  const hosts = new Set<string>();
  for (const o of [...observations].sort((a, b) => a.sampledAt - b.sampledAt)) {
    if (o.power) hosts.add(o.power.hostId);
    for (const c of o.power?.components ?? []) {
      components.set(c.id, c);
      if (now - (o.receivedAt ?? o.sampledAt) <= 30) fresh.set(c.id, c);
    }
  }
  const measured = (kind: string) => [...fresh.values()].filter((c) => c.kind === kind && c.powerW != null);
  const sum = (rows: PowerComponent[]) => (rows.length ? rows.reduce((n, c) => n + (c.powerW ?? 0), 0) : null);
  const packages = measured('cpu-package'),
    gpus = measured('gpu'),
    wall = measured('wall');
  return {
    hostCount: hosts.size,
    cpuW: sum(packages),
    gpuW: sum(gpus),
    wholeW: sum(wall),
    wholeCount: wall.length,
    componentW: sum([...fresh.values()].filter((c) => c.includedInSubtotal && c.powerW != null)),
    energyComponents: [...components.values()].filter((c) => c.includedInSubtotal && c.energy.sampledSeconds > 0),
  };
}
