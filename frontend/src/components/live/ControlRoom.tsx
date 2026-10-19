import { useProduct } from "@heteroes/product-ui";
import { Link } from "react-router";
import type { Experiment } from "../../types/experiment";
import { EmptyState } from "../common/EmptyState";
import { ExperimentLive } from "./ExperimentLive";

const ACTIVE = ["RUNNING", "STARTING", "RECOVERING", "PAUSING", "CANCELLING", "DRAINING"];

/** The centre of the dashboard: the run in progress, or a replay of the latest finished one. */
export function ControlRoom({ experiments }: { experiments: Experiment[] }) {
  const { t } = useProduct();
  const active = experiments.find(e => ACTIVE.includes(e.status));
  // For the replay, prefer the run that used the most GPUs (the most telling picture), then the newest.
  const latest = [...experiments].filter(e => e.status === "COMPLETED").sort((a, b) => (b.workerIds?.length ?? 0) - (a.workerIds?.length ?? 0) || b.createdAt.localeCompare(a.createdAt))[0];
  const shown = active ?? latest;
  if (!shown) {
    return (
      <section className="card control-room" aria-label={t("Control room")}>
        <EmptyState title={t("No experiment has run yet")} message="Create one and its live view appears here.">
          <Link className="btn pri" to="/experiments/new">{t("Create experiment")}</Link>
        </EmptyState>
      </section>
    );
  }
  return (
    <section className="card control-room" aria-label={t("Control room")}>
      <div className="ch">
        <div>
          <span className="eyebrow">{t(active ? "Running now" : "Latest finished run, replayed")}</span>
          <h2><Link to={`/experiments/${shown.experimentId}`}>{shown.name}</Link></h2>
        </div>
        <div className="acts">
          <Link className="btn" to={`/experiments/${shown.experimentId}`}>{t("Open live view")} →</Link>
          {!active && <Link className="btn pri" to="/experiments/new">+ {t("Create experiment")}</Link>}
        </div>
      </div>
      <div className="cb"><ExperimentLive experimentId={shown.experimentId} status={shown.status} variant="compact" /></div>
    </section>
  );
}
