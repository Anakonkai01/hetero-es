import {useProduct} from '@heteroes/product-ui';
import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useAppState } from "../app/appState";
import { EmptyState } from "../components/common/EmptyState";
import { QueryState } from "../components/common/QueryState";
import { Badge } from "../components/ui/Badge";
import { PageHeader } from "../components/ui/PageHeader";
import { useArtifacts } from "../hooks/useArtifacts";
import { useExperiments } from "../hooks/useExperiments";
import { formatBytes, formatDateTime } from "../lib/format";
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
  const artifactsQuery = useArtifacts();
  const experimentsQuery = useExperiments();
  const [params, setParams] = useSearchParams();
  const [type, setType] = useState<TypeFilter>("all");

  const experimentFilter = params.get("experiment") ?? "all";
  const selectedId = params.get("selected");

  const artifacts = artifactsQuery.data ?? [];
  const experiments = experimentsQuery.data ?? [];
  const experimentName = (id: string) =>
    experiments.find((e) => e.experimentId === id)?.name ?? id;

  const rows = artifacts.filter(
    (a) =>
      (experimentFilter === "all" || a.experimentId === experimentFilter) &&
      (type === "all" || a.type === type),
  );
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
            <div className="scroll">
              <div className="tw" role="table" aria-label={t("Artifacts")}>
                <div className="rowh cols-art" role="row">
                  <div className="c" role="columnheader">{t("File name")}</div>
                  <div className="c" role="columnheader">{t("Type")}</div>
                  <div className="c" role="columnheader">{t("Experiment")}</div>
                  <div className="c" role="columnheader">{t("Created")}</div>
                  <div className="c" role="columnheader">{t("Size")}</div>
                  <div className="c" role="columnheader">{t("Status")}</div>
                </div>
                {rows.map((artifact) => {
                  const isSelected = artifact.artifactId === selectedId;
                  const name = experimentName(artifact.experimentId);

                  return (
                    <div
                      className={isSelected ? "row cols-art sel" : "row cols-art"}
                      role="row"
                      key={artifact.artifactId}
                    >
                      <div className="c" role="cell">
                        <button
                          type="button"
                          className="link mono"
                          aria-pressed={isSelected}
                          onClick={() =>
                            updateParams({ selected: artifact.artifactId })
                          }
                        >
                          {artifact.name}
                        </button>
                      </div>
                      <div className="c" role="cell">
                        {ARTIFACT_TYPE_LABEL[artifact.type]}
                      </div>
                      <div className="c" role="cell">
                        <Link
                          className="link"
                          to={`/experiments/${artifact.experimentId}`}
                          state={fromArtifacts}
                          title={name}
                        >
                          {name}
                        </Link>
                      </div>
                      <div className="c mut" role="cell">
                        {formatDateTime(artifact.createdAt)}
                      </div>
                      <div className="c mono" role="cell">
                        {formatBytes(artifact.sizeBytes)}
                      </div>
                      <div className="c" role="cell">
                        <Badge info={ARTIFACT_STATUS[artifact.status]} />
                      </div>
                    </div>
                  );
                })}
              </div>
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
                  disabled={selected.status !== "READY"}
                  onClick={() => flash(`Simulated download: ${selected.name}`)}
                >
                  {t("Download (demo)")}</button>
              </div>
            </div>
          )}
        </section>
      </div>
    </QueryState>
  );
}
