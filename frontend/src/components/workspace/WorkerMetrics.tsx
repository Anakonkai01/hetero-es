import {useProduct} from '@heteroes/product-ui';
import type { Worker } from "../../types/worker";
export function WorkerMetrics({ worker: w }: { worker: Worker }) {
  const {t}=useProduct();
  const total = w.profile.vramTotalMb;
  const used = w.profile.vramFreeMb === undefined ? undefined : Math.max(0, Math.min(total, total - w.profile.vramFreeMb));
  return <div className="worker-metrics">
    <div className="metric-tile heat"><span>{t("Temperature")}</span><strong>{w.temperatureC ?? "—"}<small> {t("°C")}</small></strong></div>
    <div className="metric-tile"><span>{t("GPU utilization")}</span><strong>{w.utilizationPercent ?? "—"}<small> %</small></strong></div>
    <div className="memory-meter"><div><span>{t("VRAM usage")}</span><b>{used === undefined ? t("Unavailable") : `${(used / 1024).toFixed(1)} / ${(total / 1024).toFixed(1)} GiB`}</b></div><progress max={total} value={used ?? 0} aria-label={t("VRAM usage")} /><div className="hint">{w.profile.vramFreeMb === undefined ? t("No telemetry") : `${(w.profile.vramFreeMb / 1024).toFixed(1)} GiB available`}</div></div>
  </div>;
}
