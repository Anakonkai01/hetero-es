import { useState } from "react";
import { EmptyState } from "../components/common/EmptyState";
import { QueryState } from "../components/common/QueryState";
import { PageHeader } from "../components/ui/PageHeader";
import { WorkerTable } from "../components/workers/WorkerTable";
import { useWorkers } from "../hooks/useWorkers";
import { ADMISSION_STATUS } from "../lib/labels";
import type { AdmissionStatus } from "../types/worker";

type ActivityFilter = "all" | "online" | "offline";
type AdmissionFilter = "all" | AdmissionStatus;

const admissionOptions = Object.keys(ADMISSION_STATUS) as AdmissionStatus[];

export function WorkersPage() {
  const query = useWorkers();
  const [search, setSearch] = useState("");
  const [activity, setActivity] = useState<ActivityFilter>("all");
  const [admission, setAdmission] = useState<AdmissionFilter>("all");

  const workers = query.data ?? [];
  const needle = search.trim().toLowerCase();

  const rows = workers.filter(
    (w) =>
      (!needle ||
        w.workerId.toLowerCase().includes(needle) ||
        w.profile.gpuName.toLowerCase().includes(needle)) &&
      (activity === "all" ||
        (activity === "online") === (w.status === "ONLINE")) &&
      (admission === "all" || w.admissionStatus === admission),
  );

  function clearFilters() {
    setSearch("");
    setActivity("all");
    setAdmission("all");
  }

  return (
    <QueryState
      isPending={query.isPending}
      isError={query.isError}
      hasData={Boolean(query.data)}
      title="Could not load workers"
    >
      <PageHeader
        title="Workers"
        description="Activity (online) and admission are separate: an online worker may still be kept out of the computation."
      />

      <section className="card" aria-label="Worker list">
        <div className="filters" style={{ paddingTop: 16 }}>
          <div className="fg">
            <label htmlFor="f-wk-q">Search worker or GPU</label>
            <input
              id="f-wk-q"
              className="inp"
              type="search"
              placeholder="e.g. 5070, wk-1660"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <div className="fg">
            <label htmlFor="f-wk-s">Activity</label>
            <select
              id="f-wk-s"
              className="sel"
              value={activity}
              onChange={(event) =>
                setActivity(event.target.value as ActivityFilter)
              }
            >
              <option value="all">All</option>
              <option value="online">Online</option>
              <option value="offline">Not online</option>
            </select>
          </div>
          <div className="fg">
            <label htmlFor="f-wk-a">Admission</label>
            <select
              id="f-wk-a"
              className="sel"
              value={admission}
              onChange={(event) =>
                setAdmission(event.target.value as AdmissionFilter)
              }
            >
              <option value="all">All</option>
              {admissionOptions.map((option) => (
                <option key={option} value={option}>
                  {ADMISSION_STATUS[option].label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {workers.length === 0 ? (
          <EmptyState
            title="No workers registered"
            message="Start a worker process on a GPU machine and it will show up here."
          />
        ) : rows.length === 0 ? (
          <EmptyState title="No workers match the filters">
            <button type="button" className="btn" onClick={clearFilters}>
              Clear filters
            </button>
          </EmptyState>
        ) : (
          <WorkerTable workers={rows} />
        )}
      </section>
    </QueryState>
  );
}
