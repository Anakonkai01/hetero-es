import { Link } from "react-router";
import { shortId } from "../../lib/format";
import { useGeneration } from "../../hooks/useGeneration";
import type { Experiment } from "../../types/experiment";
import { ProgressBar } from "../ui/ProgressBar";

interface CurrentGenerationProgressProps {
  experiment: Experiment;
  linkGeneration?: boolean;
}

export function CurrentGenerationProgress({
  experiment,
  linkGeneration,
}: CurrentGenerationProgressProps) {
  const generationId = experiment.maxGenerations ? undefined : experiment.currentGenerationId;
  const { data: generation } = useGeneration(
    experiment.experimentId,
    generationId,
  );

  if (experiment.maxGenerations) return <span>{experiment.completedGenerations ?? 0}/{experiment.maxGenerations} generations completed{["RUNNING", "PAUSING"].includes(experiment.status) ? ` · ${experiment.mockCandidateProgress ?? 0}/${experiment.candidatesPerGeneration} candidates in current generation` : ""}</span>;
  if (!generationId) {
    return <span className="mut">No running generation</span>;
  }

  if (!generation) {
    return <span className="mut">Loading…</span>;
  }

  const short = shortId(generation.generationId);

  return (
    <div className="prog">
      <span>
        {linkGeneration ? (
          <Link
            className="link mono"
            to={`/experiments/${experiment.experimentId}/generations/${generation.generationId}`}
          >
            {short}
          </Link>
        ) : (
          <span className="mono">{short}</span>
        )}{" "}
        · {generation.committedCandidateCount} / {generation.candidateCount}{" "}
        committed
      </span>
      <ProgressBar
        done={generation.committedCandidateCount}
        total={generation.candidateCount}
      />
    </div>
  );
}
