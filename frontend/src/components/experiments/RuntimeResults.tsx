import { useProduct } from '@heteroes/product-ui';
import { useState } from 'react';
import { Link } from 'react-router';
import { downloadArtifact } from '../../api/client';
import { useArtifacts } from '../../hooks/useArtifacts';
import { useCandidates } from '../../hooks/useCandidates';
import { useGenerations } from '../../hooks/useGenerations';
import { auditOutcomeLines } from '../../lib/auditOutcomes';
import { fillTemplate } from '../../lib/eventText';
import { formatBytes, shortId } from '../../lib/format';
import { CANDIDATE_STATUS } from '../../lib/labels';
import type { Experiment } from '../../types/experiment';
import { Badge } from '../ui/Badge';
import { RewardChart } from './RewardChart';
export function RuntimeResults({ experiment: e }: { experiment: Experiment }) {
  const { t } = useProduct();
  const generations = useGenerations(e.experimentId),
    artifacts = useArtifacts();
  const [selection, setSelection] = useState('');
  const [error, setError] = useState('');
  const [downloading, setDownloading] = useState('');
  const gs = generations.data ?? [];
  const selected =
    gs.find((g) => g.generationId === selection) ??
    gs.find((g) => g.generationId === e.currentGenerationId) ??
    gs.at(-1);
  const candidates = useCandidates(selected?.generationId);
  const mean = gs.filter((g) => g.rewardMean !== undefined).at(-1)?.rewardMean;
  const bests = gs.flatMap((g) => (g.rewardBest === undefined ? [] : [g.rewardBest]));
  return (
    <section className="card">
      <div className="ch">
        <h2>{t('Experiment progress')}</h2>
        <small>{t('Accepted runtime results')}</small>
      </div>
      <div className="cb">
        <dl className="detail-summary">
          <div>
            <dt>{t('Completed generations')}</dt>
            <dd>
              {e.completedGenerations ?? 0} <small>/ {e.maxGenerations ?? '—'}</small>
            </dd>
          </div>
          <div>
            <dt>{t('Current accepted candidates')}</dt>
            <dd>
              {selected?.committedCandidateCount ?? e.committedCandidateCount ?? 0}{' '}
              <small>/ {selected?.candidateCount ?? e.candidatesPerGeneration}</small>
            </dd>
          </div>
          <div>
            <dt>{t('Latest mean reward')}</dt>
            <dd>{mean?.toFixed(4) ?? '—'}</dd>
          </div>
          <div>
            <dt>{t('Best candidate reward')}</dt>
            <dd>{bests.length ? Math.max(...bests).toFixed(4) : '—'}</dd>
          </div>
        </dl>
        {e.auditSummary && (
          <p className={e.auditSummary.mismatches ? 'note err' : e.auditSummary.incomplete ? 'note warn' : 'note'}>
            {t('Audits completed')}: {e.auditSummary.completed}
            {e.auditSummary.selected != null ? ` / ${e.auditSummary.selected} ${t('chosen')}` : ''}
            {e.auditSummary.incomplete ? ` · ${t('Audits not completed')}: ${e.auditSummary.incomplete}` : ''} ·{' '}
            {t('Audit mismatches')}: {e.auditSummary.mismatches} · {t('Quarantined workers')}:{' '}
            {e.auditSummary.quarantinedWorkers
              .map((worker) => e.workerIdentities?.[worker.worker_id]?.name ?? worker.worker_id)
              .join(', ') || '0'}
            {e.auditSummary.selectionComplete === false && (
              <>
                <br />
                {t('Audit selection history is incomplete; the completed count is verified.')}
              </>
            )}
          </p>
        )}
        {e.auditSummary?.outcomes &&
          auditOutcomeLines(
            e.auditSummary.outcomes,
            Object.fromEntries(Object.entries(e.workerIdentities ?? {}).map(([id, worker]) => [id, worker.name])),
          ).map((line) => (
            <p
              key={line.segments[0].template}
              className={line.tone === 'info' ? 'note' : `note ${line.tone}`}
              data-audit-outcome={line.tone}
              role={line.tone === 'err' ? 'alert' : undefined}
            >
              {line.segments.map((segment) => fillTemplate(t(segment.template), segment.params)).join(' · ')}
            </p>
          ))}
        {generations.isError && (
          <p className="note err" role="alert">
            {t('Generation history unavailable')}
          </p>
        )}
        <div className="chart-wrap">
          <div className="section-title">
            <h2>{t('Reward by generation')}</h2>
            <span className="hint">{e.task}</span>
          </div>
          <RewardChart generations={gs} />
        </div>
        <p className="info-caption">
          {e.recipeVersion === 3
            ? `${t('Best validation reward')}: ${e.validationScore ?? '—'} · ${t('Test reward')}: ${e.studyMetrics?.testLocked !== false ? t('Locked') : (e.testScore ?? '—')} · ${t('Weight space')}: ${e.weightSpace?.kind}`
            : e.recipeVersion === 2
              ? `${t('Best validation accuracy')}: ${e.validationScore ?? '—'} · ${t('Test accuracy')}: ${e.studyMetrics?.testLocked !== false ? t('Locked') : (e.testScore ?? '—')} · ${t('Export reload')}: ${e.studyMetrics?.independentReloadPassed ? t('Verified') : t('Pending')}`
              : t(
                  'Validation and test scores are unavailable: this run evaluates candidate rewards on the selected built-in workload.',
                )}
        </p>
        {e.recipeVersion === 3 && e.studyMetrics?.validation?.length ? (
          <div className="scroll">
            <table className="inspector-table">
              <thead>
                <tr>
                  <th>{t('Generation')}</th>
                  <th>{t('Validation reward')}</th>
                </tr>
              </thead>
              <tbody>
                {e.studyMetrics.validation.map((row) => (
                  <tr key={row.generation}>
                    <td>{row.generation < 0 ? t('Initial checkpoint') : row.generation}</td>
                    <td>{row.meanReward.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        <section className="experiment-inspector">
          {e.monitoringPartial && (
            <p className="note">
              {t('Candidate details are limited to recent generations. Generation summaries cover the recorded run.')}
            </p>
          )}
          <div className="generation-picker">
            <div>
              <h3>{t('Generation & candidate inspector')}</h3>
              <p>{t('Inspect seeds, allocation and accepted rewards for each generation.')}</p>
            </div>
            <label className="fg">
              <span className="sr-only">{t('Select generation')}</span>
              <select
                className="sel"
                value={selected?.generationId ?? ''}
                onChange={(event) => setSelection(event.target.value)}
                disabled={!gs.length}
              >
                {!gs.length && <option value="">{t('No generations yet')}</option>}
                {gs.map((g, i) => (
                  <option key={g.generationId} value={g.generationId}>
                    {t('Generation')} {Number(g.generationId.split('.g').at(-1) ?? i) + 1} · {t(g.status)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {selected && (
            <p className="info-caption">
              <Link to={`/experiments/${e.experimentId}/generations/${selected.generationId}`}>
                {t('Open generation')} →
              </Link>{' '}
              · <span className="mono">{selected.generationId}</span>
            </p>
          )}
          {candidates.isError ? (
            <p className="note err" role="alert">
              {t('Candidate history unavailable')}
            </p>
          ) : candidates.isPending && selected ? (
            <p role="status">{t('Loading candidates…')}</p>
          ) : candidates.data?.length ? (
            <div className="scroll">
              <table className="inspector-table">
                <thead>
                  <tr>
                    {['Candidate', 'Seed', 'Status', 'Assigned worker', 'Reward'].map((label) => (
                      <th key={label} scope="col">
                        {t(label)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {candidates.data.map((c) => (
                    <tr key={c.candidateId}>
                      <td>
                        <Link
                          className="mono"
                          to={`/experiments/${e.experimentId}/generations/${c.generationId}/candidates/${c.candidateId}`}
                        >
                          {shortId(c.candidateId)}
                        </Link>
                      </td>
                      <td className="seed">{c.seed}</td>
                      <td>
                        <Badge info={CANDIDATE_STATUS[c.status]} />
                      </td>
                      <td>
                        {c.workerId ? (
                          <Link title={c.workerId} to={`/workers/${c.workerId}`}>
                            {e.workerIdentities?.[c.workerId]?.name ?? c.workerId}
                          </Link>
                        ) : (
                          t('Not assigned')
                        )}
                      </td>
                      <td className="seed">{c.reward?.toFixed(4) ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="note">
              {t(
                e.monitoringPartial && selected?.status === 'COMPLETED'
                  ? 'Candidate details for this generation are outside the dashboard history.'
                  : 'Candidates appear after the coordinator opens a generation.',
              )}
            </p>
          )}
          <p className="info-caption">
            {t(
              'Candidate seeds are derived from the experiment, generation and candidate index. Retries reuse the same seed.',
            )}
          </p>
        </section>
        <div className="recovery-strip">
          <span>
            {t('Checkpoint sync')}: <b>{t(e.cloudSync?.status ?? 'Not reported')}</b>
          </span>
          <small>
            {t('Last synced generation')}: {e.cloudSync?.lastCloudGeneration ?? '—'}
          </small>
          <Link className="link" to={`/artifacts?experiment=${e.experimentId}`}>
            {t('View artifacts')} →
          </Link>
        </div>
        {error && (
          <p role="alert" className="note err">
            {error}
          </p>
        )}
        {artifacts.isError && (
          <p className="note err" role="alert">
            {t('Artifact list unavailable')}
          </p>
        )}
        {artifacts.data
          ?.filter((a) => a.experimentId === e.experimentId)
          .map((a) => (
            <div className="demo-item" key={a.artifactId}>
              <span>
                {a.name}
                <small className="hint">
                  {' '}
                  · {formatBytes(a.sizeBytes)} · {t(a.status)}
                </small>
              </span>
              <button
                className="btn"
                disabled={!!downloading || a.status !== 'READY'}
                onClick={() => {
                  setError('');
                  setDownloading(a.artifactId);
                  void downloadArtifact(a.artifactId, a.name)
                    .catch((err: Error) => setError(err.message))
                    .finally(() => setDownloading(''));
                }}
              >
                {t(downloading === a.artifactId ? 'Downloading…' : 'Download')}
              </button>
            </div>
          ))}
        <p className="info-caption">
          {t(
            "A checkpoint download contains canonical raw FP16 weights. Load it with Track A's schema and verified hash; it is not a standalone Hugging Face model directory.",
          )}
        </p>
      </div>
    </section>
  );
}
