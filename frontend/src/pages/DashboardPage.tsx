import { useState } from "react";
import { Link } from "react-router";
import { useAppState } from "../app/appState";
import { isServerError } from "../api/client";
import { EmptyState } from "../components/common/EmptyState";
import { ErrorState } from "../components/common/ErrorState";
import { QueryState } from "../components/common/QueryState";
import { EventRows } from "../components/events/EventRows";
import { ExperimentTable } from "../components/experiments/ExperimentTable";
import { PageHeader } from "../components/ui/PageHeader";
import { Stat } from "../components/ui/Stat";
import { WorkerTable } from "../components/workers/WorkerTable";
import { useEvents } from "../hooks/useEvents";
import { useExperiments } from "../hooks/useExperiments";
import { useWorkers } from "../hooks/useWorkers";
import { fromDashboard } from "../lib/navigation";

const DAY_MS = 24 * 60 * 60 * 1000;
const RECENT_EXPERIMENT_LIMIT = 4;
const RECENT_EVENT_LIMIT = 5;

export function DashboardPage() {
  const { retryRegion } = useAppState();
  const experimentsQuery = useExperiments();
  const workersQuery = useWorkers();
  const eventsQuery = useEvents();
  const [now] = useState(() => Date.now());

  const experiments = experimentsQuery.data ?? [];
  const workers = workersQuery.data ?? [];
  const events = eventsQuery.data ?? [];

  const lastDay = events.filter(
    (event) => now - new Date(event.timestamp).getTime() <= DAY_MS,
  );
  const errorCount = lastDay.filter((e) => e.severity === "ERROR").length;
  const warningCount = lastDay.filter((e) => e.severity === "WARNING").length;

  const active = (status: string) => status === "RUNNING" || status === "QUEUED";
  const recentExperiments = experiments
    .filter((e) => active(e.status))
    .concat(experiments.filter((e) => !active(e.status)))
    .slice(0, RECENT_EXPERIMENT_LIMIT);

  const online = workers.filter((w) => w.status === "ONLINE").length;
  const admitted = workers.filter(
    (w) =>
      w.admissionStatus === "ADMITTED" ||
      w.admissionStatus === "ADMITTED_LIMITED",
  ).length;

  const eventsFailed = eventsQuery.isError && isServerError(eventsQuery.error);

  return (
    <QueryState
      isPending={experimentsQuery.isPending || workersQuery.isPending}
      isError={experimentsQuery.isError || workersQuery.isError}
      hasData={Boolean(experimentsQuery.data && workersQuery.data)}
      title="Could not load the dashboard"
    >
      <PageHeader
        title="Dashboard"
        description="Cluster and experiment status as of the latest update."
      />

      <div className="stats">
        <Stat
          label="Running experiments"
          value={experiments.filter((e) => e.status === "RUNNING").length}
          unit={`of ${experiments.length}`}
          note="Across all recorded experiments"
        />
        <Stat
          label="Active workers (online)"
          value={online}
          unit={`of ${workers.length}`}
          note="Online does not mean admitted"
        />
        <Stat
          label="Admitted workers"
          value={admitted}
          unit={`of ${workers.length}`}
          note="Full or limited admission"
        />
        <Stat
          label="Errors / warnings (last 24 h)"
          value={errorCount}
          unit={`errors · ${warningCount} warnings`}
          note="Times in GMT+7"
        />
      </div>

      <section className="card" aria-labelledby="h-dexp">
        <div className="ch">
          <h2 id="h-dexp">Running and recent experiments</h2>
          <Link className="link" to="/experiments">
            View all experiments →
          </Link>
        </div>
        {experiments.length === 0 ? (
          <EmptyState
            title="No experiments yet"
            message="Create your first experiment to start tracking progress here."
          >
            <Link className="btn pri" to="/experiments/new">
              Create experiment
            </Link>
          </EmptyState>
        ) : (
          <ExperimentTable
            experiments={recentExperiments}
            compact
            backState={fromDashboard}
          />
        )}
      </section>

      <div className="two">
        <section className="card" aria-labelledby="h-dwk">
          <div className="ch">
            <h2 id="h-dwk">Workers</h2>
            <Link className="link" to="/workers">
              Open list →
            </Link>
          </div>
          {workers.length === 0 ? (
            <EmptyState title="No workers registered" />
          ) : (
            <WorkerTable workers={workers} compact />
          )}
        </section>

        <section className="card" aria-labelledby="h-dev">
          <div className="ch">
            <h2 id="h-dev">Recent events</h2>
            <Link className="link" to="/events">
              Open log →
            </Link>
          </div>
          {eventsFailed ? (
            <ErrorState
              title="Could not load events"
              message="The other regions are still readable."
              onRetry={retryRegion}
              retryLabel="Retry this region"
            />
          ) : events.length === 0 ? (
            <EmptyState
              title="No events yet"
              message="Events appear once experiments or workers are active."
            />
          ) : (
            <EventRows
              events={events.slice(0, RECENT_EVENT_LIMIT)}
              label="Recent events"
            />
          )}
        </section>
      </div>
    </QueryState>
  );
}
