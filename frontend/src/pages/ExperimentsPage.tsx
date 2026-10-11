import {useProduct} from '@heteroes/product-ui';
import { archiveExperiment } from "../api/experiments";
import { useAccessMutation } from "../hooks/useAccess";
import { Badge } from "../components/ui/Badge";
import { EXPERIMENT_STATUS } from "../lib/labels";
import { useState } from "react";
import { Link } from "react-router";
import { EmptyState } from "../components/common/EmptyState";
import { QueryState } from "../components/common/QueryState";
import { ExperimentTable } from "../components/experiments/ExperimentTable";
import { PlusIcon } from "../components/ui/Icons";
import { PageHeader } from "../components/ui/PageHeader";
import { useExperiments } from "../hooks/useExperiments";
import type { ExperimentStatus } from "../types/experiment";
import { IS_MOCK } from '../lib/dataSource';
import { LabQueue } from './LabQueue';

type StatusFilter = "all" | ExperimentStatus;
type SortOrder = "new" | "old";

const statusOptions: ExperimentStatus[] = [
  "STARTING", "CANCELLING", "RECOVERING", "DRAINING", "FAILED",
  "DRAFT",
  "PAUSING",
  "PAUSED",
  "RUNNING",
  "COMPLETED",
  "QUEUED",
  "CANCELLED",
];

export function ExperimentsPage() {
  const {t}=useProduct();
  const query = useExperiments();
  const archive = useAccessMutation(archiveExperiment);
  const [view, setView] = useState("grid");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [sort, setSort] = useState<SortOrder>("new");

  const experiments = query.data ?? [];
  const needle = search.trim().toLowerCase();

  const rows = experiments
    .filter(
      (e) =>
        (!needle ||
          e.name.toLowerCase().includes(needle) ||
          e.experimentId.toLowerCase().includes(needle)) &&
        (status === "all" || e.status === status),
    )
    .sort((a, b) =>
      sort === "new"
        ? b.createdAt.localeCompare(a.createdAt)
        : a.createdAt.localeCompare(b.createdAt),
    );

  function clearFilters() {
    setSearch("");
    setStatus("all");
  }

  return (
    <QueryState
      isPending={query.isPending}
      isError={query.isError}
      hasData={Boolean(query.data)}
      title={t("Could not load experiments")}
    >
      <PageHeader
        title={t("Experiments")}
        description={t("Experiments in the selected workspace.")}
        actions={
          <Link className="btn pri" to="/experiments/new">
            <PlusIcon />
            {t("Create experiment")}</Link>
        }
      />

      <div className="acts"><button className="btn" onClick={() => setView("grid")}>{t("Grid")}</button><button className="btn" onClick={() => setView("list")}>{t("List")}</button></div>
      {!IS_MOCK && <LabQueue />}
      {archive.error && <div className="note err" role="alert">{archive.error.message}</div>}
      <section className="card" aria-label={t("Experiment list")}>
        <div className="filters" style={{ paddingTop: 16 }}>
          <div className="fg">
            <label htmlFor="f-ex-q">{t("Search by name or ID")}</label>
            <input
              id="f-ex-q"
              className="inp"
              type="search"
              placeholder={t("e.g. Countdown, exp-8d21")}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <div className="fg">
            <label htmlFor="f-ex-s">{t("Status")}</label>
            <select
              id="f-ex-s"
              className="sel"
              value={status}
              onChange={(event) => setStatus(event.target.value as StatusFilter)}
            >
              <option value="all">{t("All")}</option>
              {statusOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
          <div className="fg">
            <label htmlFor="f-ex-o">{t("Sort")}</label>
            <select
              id="f-ex-o"
              className="sel"
              value={sort}
              onChange={(event) => setSort(event.target.value as SortOrder)}
            >
              <option value="new">{t("Newest first")}</option>
              <option value="old">{t("Oldest first")}</option>
            </select>
          </div>
        </div>

        {experiments.length === 0 ? (
          <EmptyState
            title={t("No experiments yet")}
            message="Create your first experiment to start an ES run."
          >
            <Link className="btn pri" to="/experiments/new">
              {t("Create experiment")}</Link>
          </EmptyState>
        ) : rows.length === 0 ? (
          <EmptyState
            title={t("No experiments match the filters")}
            message="Try a different keyword or status."
          >
            <button type="button" className="btn" onClick={clearFilters}>
              {t("Clear filters")}</button>
          </EmptyState>
        ) : (
          view === "list" ? <ExperimentTable experiments={rows} /> : <div className="resource-grid cb">{rows.map((e) => <section className="card" key={e.experimentId}><div className="ch"><h2>{e.name}</h2><Badge info={EXPERIMENT_STATUS[e.status]} /></div><div className="cb demo-form"><span>{e.modelName}</span><span>{e.task} · {e.workerIds?.length ?? 0} {t("Workers")}</span><span>{e.completedGenerations ?? 0}/{e.maxGenerations ?? "—"} {t("generations completed")}</span><div className="acts"><Link className="btn" to={`/experiments/${e.experimentId}`}>{e.status === "DRAFT" ? "Open / edit draft" : "Open dashboard"}</Link>{!["RUNNING", "QUEUED", "PAUSING", "PAUSED", "STARTING", "CANCELLING", "RECOVERING", "DRAINING"].includes(e.status) && <button className="btn dng" disabled={archive.isPending} onClick={() => { if (window.confirm("Archive this experiment?")) void archive.mutateAsync(e.experimentId).catch(() => {}); }}>{t("Delete / archive")}</button>}</div></div></section>)}</div>
        )}
      </section>

      <p className="hint" style={{ margin: 0 }}>
        {t("Times in GMT+7. Showing")}{rows.length} {t("experiments.")}</p>
    </QueryState>
  );
}
