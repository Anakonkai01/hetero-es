import { useProduct } from "@heteroes/product-ui";
import { useState } from "react";
import { useRunTimeline } from "../../hooks/useRunTimeline";
import { emptyLiveText } from "../../lib/liveEmpty";
import { EmptyState } from "../common/EmptyState";
import { ErrorState } from "../common/ErrorState";
import { LoadingState } from "../common/LoadingState";
import { RunLiveView,type LiveVariant } from "./RunLiveView";

const FINISHED = ["COMPLETED", "CANCELLED", "FAILED"];

/** Fetches (and keeps fresh) the timeline of one experiment and shows it live, or as a replay once it has finished. */
export function ExperimentLive({ experimentId, status, variant = "full" }: { experimentId: string; status: string; variant?: LiveVariant }) {
  const { t } = useProduct();
  const { timeline, source, clockOffsetMs } = useRunTimeline(experimentId);
  // Someone who watched this run while it was running should not see it rewind to the start when it ends.
  const [watchedLive, setWatchedLive] = useState(false);
  const running = Boolean(timeline) && !FINISHED.includes(timeline?.experiment.status ?? status);
  if (running && !watchedLive) setWatchedLive(true);
  if (!timeline) return source === "error" ? <ErrorState title={t("Could not load the live view")} /> : <LoadingState />;
  if (!timeline.jobs.length && !timeline.generations.length) {
    const text = emptyLiveText(timeline.experiment.status ?? status);
    return <EmptyState title={t(text.title)} message={text.message} />;
  }
  const mode = FINISHED.includes(timeline.experiment.status ?? status) ? "replay" : "live";
  return <RunLiveView key={`${experimentId}-${mode}`} timeline={timeline} mode={mode} source={source} clockOffsetMs={clockOffsetMs} title={timeline.experiment.name ?? undefined} variant={variant} afterLive={watchedLive} />;
}
