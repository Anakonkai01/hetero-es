import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { isServerError } from "../api/client";
import { useAppState } from "../app/appState";
import { EmptyState } from "../components/common/EmptyState";
import { ErrorState } from "../components/common/ErrorState";
import { QueryState } from "../components/common/QueryState";
import { Badge } from "../components/ui/Badge";
import { PageHeader } from "../components/ui/PageHeader";
import { useEvents } from "../hooks/useEvents";
import { useExperiments } from "../hooks/useExperiments";
import { formatClock, formatFullDateTime, shortId } from "../lib/format";
import { EVENT_SEVERITY } from "../lib/labels";
import { fromEvents } from "../lib/navigation";
import type { EventSeverity, SystemEvent } from "../types/event";

type LevelFilter = "all" | EventSeverity;

const WORKERS_ONLY = "workers";
const MINUTE_MS = 60_000;

interface RelatedLink {
  kind: string;
  label: string;
  to: string;
}

export function EventsPage() {
  const { retryRegion } = useAppState();
  const eventsQuery = useEvents();
  const experimentsQuery = useExperiments();
  const [params, setParams] = useSearchParams();
  const [level, setLevel] = useState<LevelFilter>("all");
  const [rangeMinutes, setRangeMinutes] = useState("all");
  const [now] = useState(() => Date.now());

  const related = params.get("experiment") ?? "all";
  const selectedId = params.get("selected");

  const events = eventsQuery.data ?? [];
  const experiments = experimentsQuery.data ?? [];

  const rows = events.filter(
    (e) =>
      (level === "all" || e.severity === level) &&
      (rangeMinutes === "all" ||
        now - new Date(e.timestamp).getTime() <=
          Number(rangeMinutes) * MINUTE_MS) &&
      (related === "all" ||
        (related === WORKERS_ONLY
          ? !e.experimentId && Boolean(e.workerId)
          : e.experimentId === related)),
  );
  const selected = events.find((e) => e.eventId === selectedId);

  function updateParams(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params);

    for (const [key, value] of Object.entries(changes)) {
      if (value === null) next.delete(key);
      else next.set(key, value);
    }

    setParams(next, { replace: true });
  }

  function clearFilters() {
    setLevel("all");
    setRangeMinutes("all");
    updateParams({ experiment: null });
  }

  function linksOf(event: SystemEvent): RelatedLink[] {
    const links: RelatedLink[] = [];
    const experimentId = event.experimentId;
    const candidatePath =
      experimentId && event.generationId && event.candidateId
        ? `/experiments/${experimentId}/generations/${event.generationId}/candidates/${event.candidateId}`
        : undefined;

    if (experimentId) {
      links.push({
        kind: "Experiment",
        label:
          experiments.find((e) => e.experimentId === experimentId)?.name ??
          shortId(experimentId),
        to: `/experiments/${experimentId}`,
      });
    }

    if (experimentId && event.generationId) {
      links.push({
        kind: "Generation",
        label: shortId(event.generationId),
        to: `/experiments/${experimentId}/generations/${event.generationId}`,
      });
    }

    if (candidatePath && event.candidateId) {
      links.push({
        kind: "Candidate",
        label: shortId(event.candidateId),
        to: candidatePath,
      });
    }

    if (candidatePath && event.attemptId) {
      links.push({
        kind: "Attempt",
        label: shortId(event.attemptId),
        to: candidatePath,
      });
    }

    if (event.workerId) {
      links.push({
        kind: "Worker",
        label: event.workerId,
        to: `/workers/${event.workerId}`,
      });
    }

    return links;
  }

  const failed = eventsQuery.isError && isServerError(eventsQuery.error);

  return (
    <QueryState
      isPending={eventsQuery.isPending}
      isError={eventsQuery.isError && !failed}
      hasData={Boolean(eventsQuery.data)}
      title="Could not load events"
    >
      <PageHeader
        title="Events"
        description="Execution log. When data refreshes automatically, your reading position is preserved."
      />

      <div className="split">
        <section className="card a" aria-label="Event log">
          <div className="filters" style={{ paddingTop: 16 }}>
            <div className="fg">
              <label htmlFor="f-ev-l">Level</label>
              <select
                id="f-ev-l"
                className="sel"
                value={level}
                onChange={(event) => setLevel(event.target.value as LevelFilter)}
              >
                <option value="all">All</option>
                <option value="ERROR">ERROR</option>
                <option value="WARNING">WARNING</option>
                <option value="INFO">INFO</option>
              </select>
            </div>
            <div className="fg">
              <label htmlFor="f-ev-r">Time</label>
              <select
                id="f-ev-r"
                className="sel"
                value={rangeMinutes}
                onChange={(event) => setRangeMinutes(event.target.value)}
              >
                <option value="all">All time</option>
                <option value="60">Last hour</option>
                <option value="1440">Last 24 hours</option>
              </select>
            </div>
            <div className="fg">
              <label htmlFor="f-ev-e">Related object</label>
              <select
                id="f-ev-e"
                className="sel"
                value={related}
                onChange={(event) =>
                  updateParams({
                    experiment:
                      event.target.value === "all" ? null : event.target.value,
                  })
                }
              >
                <option value="all">Any object</option>
                {experiments.map((experiment) => (
                  <option
                    key={experiment.experimentId}
                    value={experiment.experimentId}
                  >
                    {experiment.name}
                  </option>
                ))}
                <option value={WORKERS_ONLY}>Workers only</option>
              </select>
            </div>
          </div>

          {failed ? (
            <ErrorState
              title="Could not load the event log"
              onRetry={retryRegion}
              retryLabel="Retry this region"
            />
          ) : events.length === 0 ? (
            <EmptyState
              title="No events yet"
              message="The log fills in once experiments or workers are active."
            />
          ) : rows.length === 0 ? (
            <EmptyState title="No events match the filters">
              <button type="button" className="btn" onClick={clearFilters}>
                Clear filters
              </button>
            </EmptyState>
          ) : (
            <div className="scroll">
              <div className="tw s" role="table" aria-label="Events">
                <div className="rowh cols-ev" role="row">
                  <div className="c" role="columnheader">Time</div>
                  <div className="c" role="columnheader">Level</div>
                  <div className="c" role="columnheader">Type</div>
                  <div className="c" role="columnheader">Message</div>
                </div>
                {rows.map((event) => {
                  const isSelected = event.eventId === selectedId;

                  return (
                    <div
                      className={isSelected ? "row cols-ev sel" : "row cols-ev"}
                      role="row"
                      key={event.eventId}
                    >
                      <div className="c mono mut" role="cell">
                        {formatClock(event.timestamp)}
                      </div>
                      <div className="c" role="cell">
                        <Badge info={EVENT_SEVERITY[event.severity]} />
                      </div>
                      <div className="c mono" role="cell">
                        {event.eventType}
                      </div>
                      <div className="c" role="cell">
                        <button
                          type="button"
                          className="link"
                          style={{ whiteSpace: "normal", color: "var(--ink)" }}
                          aria-pressed={isSelected}
                          onClick={() => updateParams({ selected: event.eventId })}
                        >
                          {event.message}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </section>

        <section className="card b" aria-label="Event details">
          <div className="ch">
            <h2>Event details</h2>
          </div>
          {!selected ? (
            <div className="empty">
              <span>
                Select an event in the list to see its details and related
                objects.
              </span>
            </div>
          ) : (
            <div
              className="cb"
              style={{ display: "flex", flexDirection: "column", gap: 14 }}
            >
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 8,
                  alignItems: "center",
                }}
              >
                <Badge info={EVENT_SEVERITY[selected.severity]} />
                <span className="mono">{selected.eventType}</span>
                <span className="mono mut">
                  {formatFullDateTime(selected.timestamp)} GMT+7
                </span>
              </div>

              <div>{selected.message}</div>

              <div>
                <div className="hint" style={{ marginBottom: 4 }}>
                  Related objects
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  {linksOf(selected).map((link) => (
                    <div key={link.kind}>
                      <span className="hint">{link.kind}: </span>
                      <Link
                        className="link mono"
                        to={link.to}
                        state={fromEvents}
                      >
                        {link.label}
                      </Link>
                    </div>
                  ))}
                </div>
              </div>

              <details style={{ margin: "0 -20px" }}>
                <summary>Technical details</summary>
                <div style={{ padding: "0 20px" }}>
                  <pre className="mono">
                    {JSON.stringify(
                      { event_id: selected.eventId, ...selected.details },
                      null,
                      2,
                    )}
                  </pre>
                </div>
              </details>
            </div>
          )}
        </section>
      </div>
    </QueryState>
  );
}
