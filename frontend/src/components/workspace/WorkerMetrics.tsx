import type { Worker } from "../../types/worker";
export function WorkerMetrics({ worker: w }: { worker: Worker }) {
  const total = w.profile.vramTotalMb;
  const used = w.profile.vramFreeMb === undefined ? undefined : Math.max(0, Math.min(total, total - w.profile.vramFreeMb));
  return <div className="worker-metrics">
    <div className="metric-tile heat"><span>Temperature</span><strong>{w.temperatureC ?? "—"}<small> °C</small></strong></div>
    <div className="metric-tile"><span>GPU utilization</span><strong>{w.utilizationPercent ?? "—"}<small> %</small></strong></div>
    <div className="memory-meter"><div><span>VRAM usage</span><b>{used === undefined ? "Unavailable" : `${(used / 1024).toFixed(1)} / ${(total / 1024).toFixed(1)} GiB`}</b></div><progress max={total} value={used ?? 0} aria-label="VRAM usage" /><div className="hint">{w.profile.vramFreeMb === undefined ? "No telemetry" : `${(w.profile.vramFreeMb / 1024).toFixed(1)} GiB available`}</div></div>
  </div>;
}
