import { useProduct } from '@heteroes/product-ui';
import { Link,useParams } from "react-router";
import { isNotFoundError } from "../api/client";
import { ObjectNotFound } from "../components/common/ObjectNotFound";
import { QueryState } from "../components/common/QueryState";
import { Badge } from "../components/ui/Badge";
import { Breadcrumbs } from "../components/ui/Breadcrumbs";
import { CopyButton } from "../components/ui/CopyButton";
import { KeyValue } from "../components/ui/KeyValue";
import { PageHeader,PageHeaderMeta } from "../components/ui/PageHeader";
import { ProgressBar } from "../components/ui/ProgressBar";
import { useAttempt } from "../hooks/useAttempt";
import { useCandidates } from "../hooks/useCandidates";
import { useExperiment } from "../hooks/useExperiment";
import { useGeneration } from "../hooks/useGeneration";
import { formatOptionalDateTime,formatReward,shortId } from "../lib/format";
import {
ATTEMPT_STATUS,
CANDIDATE_LEGEND,
CANDIDATE_STATUS,
EXPERIMENT_STATUS,
} from "../lib/labels";
import type { Candidate,CandidateStatus } from "../types/candidate";

const legendOrder: CandidateStatus[] = [
  "PENDING",
  "LEASED",
  "RUNNING",
  "COMMITTED",
];

function AttemptCell({ attemptId }: { attemptId?: string }) {
  const {t}=useProduct();
  const { data: attempt } = useAttempt(attemptId);

  if (!attemptId) {
    return <span className="mut">{t("Not started")}</span>;
  }

  return (
    <>
      <span className="mono">{shortId(attemptId)}</span>{" "}
      {attempt && <Badge info={ATTEMPT_STATUS[attempt.status]} />}
    </>
  );
}

function CandidateRow({
  candidate,
  experimentId,
}: {
  candidate: Candidate;
  experimentId: string;
}) {
  const {t}=useProduct();
  return (
    <div className="row cols-cand" role="row">
      <div className="c" role="cell">
        <Link
          className="link mono"
          title={candidate.candidateId}
          to={`/experiments/${experimentId}/generations/${candidate.generationId}/candidates/${candidate.candidateId}`}
        >
          {shortId(candidate.candidateId)}
        </Link>
      </div>
      <div className="c mono" role="cell">{candidate.seed}</div>
      <div className="c" role="cell">
        <Badge info={CANDIDATE_STATUS[candidate.status]} />
      </div>
      <div className="c" role="cell">
        {candidate.workerId ? (
          <Link className="link mono" to={`/workers/${candidate.workerId}`}>
            {candidate.workerId}
          </Link>
        ) : (
          <span className="mut">{t("Not assigned")}</span>
        )}
      </div>
      <div className="c" role="cell">
        <AttemptCell attemptId={candidate.attemptId} />
      </div>
      <div className="c mono" role="cell">
        {candidate.reward?.toFixed(3) ?? "—"}
      </div>
    </div>
  );
}

export function GenerationDetailPage() {
  const {t}=useProduct();
  const { experimentId = "", generationId = "" } = useParams();

  const experimentQuery = useExperiment(experimentId);
  const generationQuery = useGeneration(experimentId, generationId);
  const candidatesQuery = useCandidates(generationId);

  if (
    isNotFoundError(generationQuery.error) ||
    isNotFoundError(experimentQuery.error)
  ) {
    return <ObjectNotFound backTo="/experiments" backLabel="Back to Experiments" />;
  }

  const generation = generationQuery.data;
  const experiment = experimentQuery.data;
  const candidates = candidatesQuery.data ?? [];
  const backToExperiment = `/experiments/${experimentId}`;

  return (
    <QueryState
      isPending={generationQuery.isPending}
      isError={generationQuery.isError}
      hasData={Boolean(generation)}
      title={t("Could not load the generation")}
    >
      {generation && (
        <>
          <Breadcrumbs
            crumbs={[
              { label: "Experiments", to: "/experiments" },
              {
                label: experiment?.name ?? shortId(experimentId),
                title: experimentId,
                to: backToExperiment,
              },
              {
                label: `Generation ${shortId(generationId)}`,
                title: generationId,
              },
            ]}
          />

          <PageHeader
            title={
              <>
                {t("Generation")}{" "}
                <span className="mono" style={{ fontSize: 20 }}>
                  {shortId(generationId)}
                </span>
              </>
            }
            meta={
              <PageHeaderMeta>
                <Badge info={EXPERIMENT_STATUS[generation.status]} />
                <span className="mono">{generationId}</span>
                <CopyButton value={generationId} subject="generation" />
              </PageHeaderMeta>
            }
            actions={
              <Link className="btn" to={backToExperiment}>
                {t("← Back to experiment")}</Link>
            }
          />

          <section className="card">
            <div className="cb" style={{ paddingTop: 20 }}>
              <dl className="kv">
                <KeyValue label={t("Model version")} mono>
                  {generation.modelVersion}
                </KeyValue>
                <KeyValue label={t("Candidates COMMITTED")}>
                  <div className="prog">
                    <span>
                      {generation.committedCandidateCount} /{" "}
                      {generation.candidateCount}
                    </span>
                    <ProgressBar
                      done={generation.committedCandidateCount}
                      total={generation.candidateCount}
                    />
                  </div>
                </KeyValue>
                <KeyValue label={t("Mean reward")} mono>
                  {formatReward(generation.rewardMean)}
                </KeyValue>
                <KeyValue label={t("Best reward")} mono>
                  {formatReward(generation.rewardBest)}
                </KeyValue>
                <KeyValue label={t("Started")}>
                  {formatOptionalDateTime(generation.startedAt, "Not available yet")}
                </KeyValue>
                <KeyValue label={t("Ended")}>
                  {formatOptionalDateTime(generation.completedAt, "Not ended")}
                </KeyValue>
              </dl>
            </div>
          </section>

          <section className="card" aria-label={t("Candidates")}>
            <div className="ch">
              <h2>{t("Candidates in this generation")}</h2>
              <small>{t("Detailed timing, network and sync data: not available yet.")}</small>
            </div>
            <div className="scroll">
              <div className="tw s" role="table" aria-label={t("Candidates")}>
                <div className="rowh cols-cand" role="row">
                  <div className="c" role="columnheader">{t("Candidate")}</div>
                  <div className="c" role="columnheader">{t("Seed")}</div>
                  <div className="c" role="columnheader">{t("Status")}</div>
                  <div className="c" role="columnheader">{t("Assigned worker")}</div>
                  <div className="c" role="columnheader">{t("Attempt")}</div>
                  <div className="c" role="columnheader">{t("Reward")}</div>
                </div>
                {candidates.map((candidate) => (
                  <CandidateRow
                    key={candidate.candidateId}
                    candidate={candidate}
                    experimentId={experimentId}
                  />
                ))}
              </div>
            </div>
          </section>

          <details className="card">
            <summary>{t("What the candidate statuses mean")}</summary>
            <div className="leg">
              {legendOrder.map((status) => (
                <div key={status}>
                  <Badge info={CANDIDATE_STATUS[status]} title="" />
                  <span className="t">{CANDIDATE_LEGEND[status]}</span>
                </div>
              ))}
            </div>
          </details>
        </>
      )}
    </QueryState>
  );
}
