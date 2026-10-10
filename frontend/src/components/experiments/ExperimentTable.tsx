import { Link } from "react-router";
import { formatDateTime, shortId } from "../../lib/format";
import { EXPERIMENT_STATUS } from "../../lib/labels";
import type { BackState } from "../../lib/navigation";
import type { Experiment } from "../../types/experiment";
import { Badge } from "../ui/Badge";
import { CurrentGenerationProgress } from "./CurrentGenerationProgress";

interface ExperimentTableProps {
  experiments: Experiment[];
  /** The compact variant is used on the dashboard. */
  compact?: boolean;
  backState?: BackState;
}

export function ExperimentTable({
  experiments,
  compact,
  backState,
}: ExperimentTableProps) {
  const columns = compact ? "cols-dexp" : "cols-exp";

  return (
    <div className="scroll">
      <div
        className={compact ? "tw s" : "tw"}
        role="table"
        aria-label={compact ? "Recent experiments" : "Experiments"}
      >
        <div className={`rowh ${columns}`} role="row">
          <div className="c" role="columnheader">
            {compact ? "Experiment" : "Name"}
          </div>
          <div className="c" role="columnheader">Status</div>
          <div className="c" role="columnheader">Model</div>
          {!compact && (
            <div className="c" role="columnheader">Scheduling policy</div>
          )}
          <div className="c" role="columnheader">
            {compact ? "Current generation progress" : "Current generation"}
          </div>
          {!compact && (
            <div className="c" role="columnheader">Created</div>
          )}
        </div>

        {experiments.map((experiment) => (
          <div
            className={`row ${columns}`}
            role="row"
            key={experiment.experimentId}
          >
            <div className="c" role="cell">
              <Link
                className="link"
                style={{
                  fontWeight: 500,
                  color: "var(--ink)",
                  whiteSpace: compact ? undefined : "normal",
                }}
                to={`/experiments/${experiment.experimentId}`}
                state={backState}
              >
                {experiment.name}
              </Link>
              <div className="mono mut">{shortId(experiment.experimentId)}</div>
            </div>

            <div className="c" role="cell">
              <Badge info={EXPERIMENT_STATUS[experiment.status]} />
              {!compact &&
                experiment.cancelRequested &&
                experiment.status === "RUNNING" && (
                  <div className="hint">Cancel requested</div>
                )}
            </div>

            <div className="c" role="cell">{experiment.modelName}</div>

            {!compact && (
              <div className="c mono" role="cell">
                {experiment.schedulerPolicy}
              </div>
            )}

            <div className="c" role="cell">
              <CurrentGenerationProgress
                experiment={experiment}
                linkGeneration={compact}
              />
            </div>

            {!compact && (
              <div className="c mut" role="cell">
                {formatDateTime(experiment.createdAt)}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
