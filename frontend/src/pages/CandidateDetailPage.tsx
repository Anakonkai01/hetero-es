import { Link, useParams } from "react-router";
import { isNotFoundError, isServerError } from "../api/client";
import { useAppState } from "../app/appState";
import { EmptyState } from "../components/common/EmptyState";
import { ErrorState } from "../components/common/ErrorState";
import { ObjectNotFound } from "../components/common/ObjectNotFound";
import { QueryState } from "../components/common/QueryState";
import { EventRows } from "../components/events/EventRows";
import { Badge } from "../components/ui/Badge";
import { Breadcrumbs } from "../components/ui/Breadcrumbs";
import { CopyButton } from "../components/ui/CopyButton";
import { KeyValue } from "../components/ui/KeyValue";
import { PageHeader, PageHeaderMeta } from "../components/ui/PageHeader";
import { useAttempt } from "../hooks/useAttempt";
import { useCandidate } from "../hooks/useCandidate";
import { useEvents } from "../hooks/useEvents";
import { useExperiment } from "../hooks/useExperiment";
import { NOT_AVAILABLE, formatClock, formatDateTime, shortId } from "../lib/format";
import { ATTEMPT_STATUS, CANDIDATE_STATUS } from "../lib/labels";

export function CandidateDetailPage() {
  const { experimentId = "", generationId = "", candidateId = "" } =
    useParams();
  const { retryRegion } = useAppState();

  const experimentQuery = useExperiment(experimentId);
  const candidateQuery = useCandidate(candidateId);
  const attemptQuery = useAttempt(candidateQuery.data?.attemptId);
  const eventsQuery = useEvents();

  if (
    isNotFoundError(candidateQuery.error) ||
    isNotFoundError(experimentQuery.error)
  ) {
    return <ObjectNotFound backTo="/experiments" backLabel="Back to Experiments" />;
  }

  const candidate = candidateQuery.data;
  const attempt = attemptQuery.data;
  const events = (eventsQuery.data ?? []).filter(
    (event) => event.candidateId === candidateId,
  );
  const attemptFailed = attemptQuery.isError && isServerError(attemptQuery.error);
  const backToGeneration = `/experiments/${experimentId}/generations/${generationId}`;
  const status = candidate ? CANDIDATE_STATUS[candidate.status] : undefined;

  return (
    <QueryState
      isPending={candidateQuery.isPending}
      isError={candidateQuery.isError}
      hasData={Boolean(candidate)}
      title="Could not load the candidate"
    >
      {candidate && status && (
        <>
          <Breadcrumbs
            crumbs={[
              { label: "Experiments", to: "/experiments" },
              {
                label: experimentQuery.data?.name ?? shortId(experimentId),
                title: experimentId,
                to: `/experiments/${experimentId}`,
              },
              {
                label: `Generation ${shortId(generationId)}`,
                title: generationId,
                to: backToGeneration,
              },
              {
                label: `Candidate ${shortId(candidateId)}`,
                title: candidateId,
              },
            ]}
          />

          <PageHeader
            title={
              <>
                Candidate{" "}
                <span className="mono" style={{ fontSize: 20 }}>
                  {shortId(candidateId)}
                </span>
              </>
            }
            meta={
              <PageHeaderMeta>
                <Badge info={status} />
                <span className="mono">{candidateId}</span>
                <CopyButton value={candidateId} subject="candidate" />
              </PageHeaderMeta>
            }
            actions={
              <Link className="btn" to={backToGeneration}>
                ← Back to generation
              </Link>
            }
          />

          <div className="note">
            <b>{candidate.status}:</b> {status.title}. A worker finishing its
            computation does not mean the result was accepted; only COMMITTED
            means accepted by the system.
          </div>

          <section className="card">
            <div className="cb" style={{ paddingTop: 20 }}>
              <dl className="kv">
                <KeyValue label="Model version" mono>
                  {candidate.modelVersion}
                </KeyValue>
                <KeyValue label="Assigned worker">
                  {candidate.workerId ? (
                    <Link
                      className="link mono"
                      to={`/workers/${candidate.workerId}`}
                    >
                      {candidate.workerId}
                    </Link>
                  ) : (
                    <span className="mut">Not assigned</span>
                  )}
                </KeyValue>
                <KeyValue label="Reward" mono>
                  {candidate.reward?.toFixed(3) ?? NOT_AVAILABLE}
                </KeyValue>
                <KeyValue label="Generation">
                  <Link className="link mono" to={backToGeneration}>
                    {shortId(generationId)}
                  </Link>
                </KeyValue>
              </dl>
            </div>

            <details style={{ borderTop: "1px solid var(--line2)" }}>
              <summary>Technical details</summary>
              <div className="cb" style={{ paddingTop: 0 }}>
                <dl className="kv">
                  <KeyValue label="Seed" mono>{candidate.seed}</KeyValue>
                  <KeyValue label="Batch IDs" mono>
                    {candidate.batchIds.join(", ")}
                  </KeyValue>
                  <KeyValue label="Config hash" mono>
                    {candidate.generationConfigHash}
                  </KeyValue>
                  <KeyValue label="Lease deadline (GMT+7)" mono>
                    {candidate.leaseDeadline
                      ? formatDateTime(candidate.leaseDeadline)
                      : NOT_AVAILABLE}
                  </KeyValue>
                </dl>
              </div>
            </details>
          </section>

          <section className="card" aria-label="Attempt">
            <div className="ch">
              <h2>Attempt</h2>
              <small>
                An attempt is one execution of the candidate on a worker.
                Showing the latest attempt the system provides.
              </small>
            </div>

            {attemptFailed ? (
              <ErrorState
                title="Could not load the attempt"
                message="The candidate information above is still readable."
                onRetry={retryRegion}
              />
            ) : !candidate.attemptId ? (
              <EmptyState
                title="Not started"
                message="This candidate has no attempt yet."
              />
            ) : attempt ? (
              <>
                <div className="scroll">
                  <div className="tw s" role="table" aria-label="Attempt">
                    <div className="rowh cols-att" role="row">
                      <div className="c" role="columnheader">Attempt</div>
                      <div className="c" role="columnheader">Worker</div>
                      <div className="c" role="columnheader">Status</div>
                      <div className="c" role="columnheader">Started</div>
                      <div className="c" role="columnheader">Ended</div>
                      <div className="c" role="columnheader">Error kind</div>
                    </div>
                    <div
                      className={
                        attempt.status === "FAILED"
                          ? "row cols-att sel"
                          : "row cols-att"
                      }
                      role="row"
                    >
                      <div className="c mono" role="cell" title={attempt.attemptId}>
                        {shortId(attempt.attemptId)}
                      </div>
                      <div className="c" role="cell">
                        <Link
                          className="link mono"
                          to={`/workers/${attempt.workerId}`}
                        >
                          {attempt.workerId}
                        </Link>
                      </div>
                      <div className="c" role="cell">
                        <Badge info={ATTEMPT_STATUS[attempt.status]} title="" />
                      </div>
                      <div className="c mono" role="cell">
                        {formatClock(attempt.startedAt)}
                      </div>
                      <div className="c mono" role="cell">
                        {attempt.completedAt ? formatClock(attempt.completedAt) : "—"}
                      </div>
                      <div className="c mono" role="cell">
                        {attempt.errorType ?? "—"}
                      </div>
                    </div>
                  </div>
                </div>

                {attempt.status === "FAILED" && (
                  <div className="cb" style={{ paddingTop: 12 }}>
                    <div className="note err">
                      <b>The attempt failed.</b> The candidate remains{" "}
                      {candidate.status} and is waiting to be reassigned. Only
                      one attempt is provided by the system; there is no
                      multi-attempt history yet.
                    </div>
                  </div>
                )}
              </>
            ) : (
              <EmptyState title="Loading the attempt…" />
            )}
          </section>

          <section className="card" aria-label="Related events">
            <div className="ch">
              <h2>Related events</h2>
            </div>
            {events.length === 0 ? (
              <EmptyState title="No related events" />
            ) : (
              <EventRows events={events} label="Related events" />
            )}
          </section>
        </>
      )}
    </QueryState>
  );
}
