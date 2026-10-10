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
import { KeyValue } from "../components/ui/KeyValue";
import { PageHeader, PageHeaderMeta } from "../components/ui/PageHeader";
import { ProgressBar } from "../components/ui/ProgressBar";
import { WorkerActivityBadge } from "../components/ui/WorkerActivity";
import { useEvents } from "../hooks/useEvents";
import { useWorker } from "../hooks/useWorker";
import { NOT_AVAILABLE, formatClock, formatGb } from "../lib/format";
import { ADMISSION_LEGEND, ADMISSION_STATUS } from "../lib/labels";

export function WorkerDetailPage() {
  const { workerId = "" } = useParams();
  const { retryRegion } = useAppState();
  const workerQuery = useWorker(workerId);
  const eventsQuery = useEvents();

  if (isNotFoundError(workerQuery.error)) {
    return <ObjectNotFound backTo="/workers" backLabel="Back to Workers" />;
  }

  const worker = workerQuery.data;
  const events = (eventsQuery.data ?? []).filter(
    (event) => event.workerId === workerId,
  );
  const eventsFailed = eventsQuery.isError && isServerError(eventsQuery.error);

  return (
    <QueryState
      isPending={workerQuery.isPending}
      isError={workerQuery.isError}
      hasData={Boolean(worker)}
      title="Could not load the worker"
    >
      {worker && (
        <>
          <Breadcrumbs
            crumbs={[
              { label: "Workers", to: "/workers" },
              { label: worker.workerId },
            ]}
          />

          <PageHeader
            title={
              <span className="mono" style={{ fontSize: 22 }}>
                {worker.workerId}
              </span>
            }
            meta={
              <PageHeaderMeta>
                <WorkerActivityBadge status={worker.status} />
                <Badge
                  info={ADMISSION_STATUS[worker.admissionStatus]}
                  label={`Admission: ${ADMISSION_STATUS[worker.admissionStatus].label}`}
                />
                <span>{worker.profile.gpuName}</span>
              </PageHeaderMeta>
            }
            actions={
              <Link className="btn" to="/workers">
                ← Back to Workers
              </Link>
            }
          />

          <div className="two">
            <section className="card" aria-label="GPU profile">
              <div className="ch">
                <h2>GPU profile</h2>
              </div>
              <div className="cb">
                <dl className="kv">
                  <KeyValue label="GPU">{worker.profile.gpuName}</KeyValue>
                  <KeyValue label="Total VRAM">
                    {formatGb(worker.profile.vramTotalMb)}
                  </KeyValue>
                  <KeyValue label="Free VRAM">
                    {worker.profile.vramFreeMb === undefined
                      ? NOT_AVAILABLE
                      : formatGb(worker.profile.vramFreeMb, 1)}
                  </KeyValue>
                  <KeyValue label="Throughput">
                    {worker.profile.throughputTokensPerSecond === undefined
                      ? NOT_AVAILABLE
                      : `${worker.profile.throughputTokensPerSecond.toLocaleString("en-US")} tokens/s`}
                  </KeyValue>
                  <KeyValue label="Safe chunk size">
                    {worker.profile.safeChunkSize === undefined
                      ? NOT_AVAILABLE
                      : `${worker.profile.safeChunkSize} candidates / round`}
                  </KeyValue>
                  <KeyValue label="Last heartbeat (GMT+7)" mono>
                    {formatClock(worker.lastHeartbeatAt)}
                  </KeyValue>
                </dl>

                {worker.profile.vramFreeMb !== undefined && (
                  <div className="prog" style={{ marginTop: 16 }}>
                    <span>
                      VRAM in use:{" "}
                      {(
                        (worker.profile.vramTotalMb -
                          worker.profile.vramFreeMb) /
                        1024
                      ).toFixed(1)}{" "}
                      / {formatGb(worker.profile.vramTotalMb)}
                    </span>
                    <ProgressBar
                      large
                      done={
                        worker.profile.vramTotalMb - worker.profile.vramFreeMb
                      }
                      total={worker.profile.vramTotalMb}
                    />
                  </div>
                )}

                <p className="hint" style={{ marginBottom: 0 }}>
                  A stale heartbeat alone is not treated as the worker being
                  down; there is no official rule yet.
                </p>
              </div>
            </section>

            <section className="card" aria-label="Admission">
              <div className="ch">
                <h2>Admission</h2>
                <small>Reason supplied by the coordinator (demo)</small>
              </div>
              <div className="cb">
                <Badge info={ADMISSION_STATUS[worker.admissionStatus]} />
                <p style={{ margin: "10px 0 0" }}>{worker.admissionReason}</p>
              </div>
              <div
                className="ch"
                style={{ borderTop: "1px solid var(--line2)" }}
              >
                <h2 style={{ fontSize: 13 }}>The four admission outcomes</h2>
              </div>
              <div className="leg">
                {ADMISSION_LEGEND.map((item) => (
                  <div
                    key={item.status}
                    className={
                      item.status === worker.admissionStatus ? "cur" : undefined
                    }
                  >
                    <Badge info={ADMISSION_STATUS[item.status]} title="" />
                    <span className="t">{item.text}</span>
                  </div>
                ))}
              </div>
            </section>
          </div>

          <section className="card" aria-label="Worker events">
            <div className="ch">
              <h2>Events related to this worker</h2>
            </div>
            {eventsFailed ? (
              <ErrorState
                title="Could not load events"
                onRetry={retryRegion}
                retryLabel="Retry this region"
              />
            ) : events.length === 0 ? (
              <EmptyState title="No related events" />
            ) : (
              <EventRows events={events} label="Worker events" />
            )}
          </section>
        </>
      )}
    </QueryState>
  );
}
