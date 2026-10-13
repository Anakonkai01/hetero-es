import { useProduct } from "@heteroes/product-ui";
import { useRunTimeline } from "../../hooks/useRunTimeline";
import { EmptyState } from "../common/EmptyState";
import { ErrorState } from "../common/ErrorState";
import { LoadingState } from "../common/LoadingState";
import { RunLiveView, type LiveVariant } from "./RunLiveView";

const FINISHED = ["COMPLETED", "CANCELLED", "FAILED"];

/** Fetches (and keeps fresh) the timeline of one experiment and shows it live, or as a replay once it has finished. */
export function ExperimentLive({ experimentId, status, variant = "full" }: { experimentId: string; status: string; variant?: LiveVariant }) {
  const { t } = useProduct();
  const { timeline, source, clockOffsetMs } = useRunTimeline(experimentId);
  if (!timeline) return source === "error" ? <ErrorState title={t("Could not load the live view")} /> : <LoadingState />;
  if (!timeline.jobs.length && !timeline.generations.length) {
    return <EmptyState title={t("Nothing has run yet")} message={FINISHED.includes(status) ? "This experiment ended before any candidate ran." : "The live view starts as soon as the coordinator hands out the first candidate."} />;
  }
  const mode = FINISHED.includes(timeline.experiment.status ?? status) ? "replay" : "live";
  return <RunLiveView key={`${experimentId}-${mode}`} timeline={timeline} mode={mode} source={source} clockOffsetMs={clockOffsetMs} title={timeline.experiment.name ?? undefined} variant={variant} />;
}
