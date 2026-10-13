import {downloadArtifact} from "../api/client";
import {IS_MOCK} from "../lib/dataSource";
import {useProduct} from '@heteroes/product-ui';
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useAppState } from "../app/appState";
import { EmptyState } from "../components/common/EmptyState";
import { QueryState } from "../components/common/QueryState";
import { Badge } from "../components/ui/Badge";
import { PageHeader } from "../components/ui/PageHeader";
import { useArtifacts } from "../hooks/useArtifacts";
import { useExperiments } from "../hooks/useExperiments";
import { formatBytes, formatDateTime } from "../lib/format";
import { friendlyFileName } from "../lib/files";
import {
  ARTIFACT_NOTE,
  ARTIFACT_STATUS,
  ARTIFACT_TYPE_LABEL,
} from "../lib/labels";
import { fromArtifacts } from "../lib/navigation";
import type { ArtifactType } from "../types/artifact";

type TypeFilter = "all" | ArtifactType;

const typeOptions = Object.keys(ARTIFACT_TYPE_LABEL) as ArtifactType[];

export function ArtifactsPage() {
  const {t}=useProduct();
  const { flash } = useAppState();
  const [downloadError,setDownloadError]=useState("");
  const [downloading,setDownloading]=useState(false);
  const artifactsQuery = useArtifacts();
  const experimentsQuery = useExperiments();
  const [params, setParams] = useSearchParams();
  const [type, setType] = useState<TypeFilter>("all");
  const [search, setSearch] = useState("");

  const experimentFilter = params.get("experiment") ?? "all";
  const selectedId = params.get("selected");

  const artifacts = artifactsQuery.data ?? [];
  const experiments = experimentsQuery.data ?? [];
  const experimentName = (id: string) =>
    experiments.find((e) => e.experimentId === id)?.name ?? id;

  const rows = artifacts.filter(
    (a) =>
      (experimentFilter === "all" || a.experimentId === experimentFilter) &&
      (type === "all" || a.type === type) &&
      (!search.trim() || a.name.toLowerCase().includes(search.trim().toLowerCase())),
  );
  // One block per experiment, newest first, instead of one endless table.
  const groups = useMemo(() => {
    const order = new Map(experiments.map((e, index) => [e.experimentId, { index, at: e.createdAt ?? "" }]));
    const byRun = new Map<string, typeof rows>();
    for (const artifact of rows) byRun.set(artifact.experimentId, [...(byRun.get(artifact.experimentId) ?? []), artifact]);
    return [...byRun.entries()]
      .sort(([a], [b]) => (order.get(b)?.at ?? "").localeCompare(order.get(a)?.at ?? "") || (order.get(b)?.index ?? 0) - (order.get(a)?.index ?? 0))
      .map(([experimentId, files]) => ({ experimentId, files: [...files].sort((x, y) => (y.createdAt ?? "").localeCompare(x.createdAt ?? "")) }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [artifacts, experiments, experimentFilter, type, search]);
  const selected = artifacts.find((a) => a.artifactId === selectedId);

  function updateParams(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params);

    for (const [key, value] of Object.entries(changes)) {
      if (value === null) next.delete(key);
      else next.set(key, value);
    }

    setParams(next, { replace: true });
  }

  function clearFilters() {
    setType("all");
    setSearch("");
    updateParams({ experiment: null });
  }

  return (
    <QueryState
      isPending={artifactsQuery.isPending}
      isError={artifactsQuery.isError}
      hasData={Boolean(artifactsQuery.data)}
      title={t("Could not load artifacts")}
    >
      <PageHeader
        title={t("Artifacts")}
        description={t("Files tied to experiments: configs, checkpoints, manifests and evaluation results.")}
      />

      {downloadError&&<div className="note err" role="alert">{downloadError}</div>}
      <div className="split">
        <section className="card a" aria-label={t("Artifact list")}>
          <div className="filters" style={{ paddingTop: 16 }}>
            <div className="fg">
              <label htmlFor="f-ar-e">{t("Experiment")}</label>
              <select
                id="f-ar-e"
                className="sel"
                value={experimentFilter}
                onChange={(event) =>
                  updateParams({
                    experiment:
                      event.target.value === "all" ? null : event.target.value,
                  })
                }
              >
                <option value="all">{t("All")}</option>
                {experiments.map((experiment) => (
                  <option
                    key={experiment.experimentId}
                    value={experiment.experimentId}
                  >
                    {experiment.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="fg">
              <label htmlFor="f-ar-q">{t("Search")}</label>
              <input id="f-ar-q" className="inp" type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("File name")} />
            </div>
            <div className="fg">
              <label htmlFor="f-ar-t">{t("File type")}</label>
              <select
                id="f-ar-t"
                className="sel"
                value={type}
                onChange={(event) => setType(event.target.value as TypeFilter)}
              >
                <option value="all">{t("All")}</option>
                {typeOptions.map((option) => (
                  <option key={option} value={option}>
                    {ARTIFACT_TYPE_LABEL[option]}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {artifacts.length === 0 ? (
            <EmptyState
              title={t("No artifacts yet")}
              message="Files appear once an experiment produces configs, checkpoints or results."
            />
          ) : rows.length === 0 ? (
            <EmptyState title={t("No artifacts match the filters")}>
              <button type="button" className="btn" onClick={clearFilters}>
                {t("Clear filters")}</button>
            </EmptyState>
          ) : (
            <div className="artifact-groups">
              {groups.map(({ experimentId, files }, index) => {
                const total = files.reduce((sum, file) => sum + (file.sizeBytes ?? 0), 0);
                return (
                  <details className="artifact-group" key={experimentId} open={index < 2 || experimentFilter !== "all" || files.some((file) => file.artifactId === selectedId)}>
                    <summary>
                      <span className="artifact-group-name">{experimentName(experimentId)}</span>
                      <span className="hint">{files.length} {t("files")} · {formatBytes(total)} · {formatDateTime(files[0]?.createdAt)}</span>
                    </summary>
                    <div role="table" aria-label={experimentName(experimentId)}>
                      {files.map((artifact) => {
                        const isSelected = artifact.artifactId === selectedId;
                        return (
                          <div className={isSelected ? "row cols-art sel" : "row cols-art"} role="row" key={artifact.artifactId}>
                            <div className="c" role="cell">
                              <button type="button" className="link mono" title={artifact.name} aria-pressed={isSelected} onClick={() => updateParams({ selected: artifact.artifactId })}>
                                {friendlyFileName(artifact.name)}
                              </button>
                            </div>
                            <div className="c" role="cell">{t(ARTIFACT_TYPE_LABEL[artifact.type])}</div>
                            <div className="c mono" role="cell">{formatBytes(artifact.sizeBytes)}</div>
                            <div className="c" role="cell"><Badge info={ARTIFACT_STATUS[artifact.status]} /></div>
                          </div>
                        );
                      })}
                    </div>
                  </details>
                );
              })}
            </div>
          )}
        </section>

        <section className="card b" aria-label={t("Artifact metadata")}>
          <div className="ch">
            <h2>{t("File details")}</h2>
          </div>
          {!selected ? (
            <div className="empty">
              <span>{t("Select a file to see its metadata and download it.")}</span>
            </div>
          ) : (
            <div
              className="cb"
              style={{ display: "flex", flexDirection: "column", gap: 14 }}
            >
              <div>
                <div
                  className="mono"
                  style={{ fontSize: 14, overflowWrap: "anywhere" }}
                >
                  {selected.name}
                </div>
                <span style={{ display: "inline-block", marginTop: 6 }}>
                  <Badge info={ARTIFACT_STATUS[selected.status]} />
                </span>
              </div>

              <dl className="kv" style={{ gridTemplateColumns: "1fr 1fr" }}>
                <div>
                  <dt>{t("Type")}</dt>
                  <dd>{ARTIFACT_TYPE_LABEL[selected.type]}</dd>
                </div>
                <div>
                  <dt>{t("Size")}</dt>
                  <dd className="mono">{formatBytes(selected.sizeBytes)}</dd>
                </div>
                <div>
                  <dt>{t("Created")}</dt>
                  <dd>{formatDateTime(selected.createdAt)}</dd>
                </div>
                <div>
                  <dt>{t("Experiment")}</dt>
                  <dd>
                    <Link
                      className="link"
                      to={`/experiments/${selected.experimentId}`}
                      state={fromArtifacts}
                    >
                      {experimentName(selected.experimentId)}
                    </Link>
                  </dd>
                </div>
              </dl>

              <div>
                <div className="hint">{t("Storage location (internal)")}</div>
                <div className="mono" style={{ overflowWrap: "anywhere" }}>
                  {selected.path}
                </div>
              </div>

              <div className={`note ${ARTIFACT_NOTE[selected.status].tone}`}>
                {ARTIFACT_NOTE[selected.status].text}
              </div>

              <div className="acts">
                <button
                  type="button"
                  className="btn pri"
                  disabled={selected.status !== "READY"||downloading}
                  onClick={() => {if(IS_MOCK){flash(`Simulated download: ${selected.name}`);return;}setDownloadError("");setDownloading(true);void downloadArtifact(selected.artifactId,selected.name).catch((e:Error)=>setDownloadError(e.message)).finally(()=>setDownloading(false));}}
                >
                  {t(downloading?"Downloading…":IS_MOCK?"Download (demo)":"Download")}</button>
              </div>
            </div>
          )}
        </section>
      </div>
    </QueryState>
  );
}
