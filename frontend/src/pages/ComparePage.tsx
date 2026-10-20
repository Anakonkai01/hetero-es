import { useProduct } from '@heteroes/product-ui';
import { useQueries } from '@tanstack/react-query';
import { useMemo, useRef } from 'react';
import { Link, useSearchParams } from 'react-router';
import { apiGet } from '../api/client';
import { useScopeKey } from '../app/session';
import { EmptyState } from '../components/common/EmptyState';
import { LoadingState } from '../components/common/LoadingState';
import { CompareChart } from '../components/experiments/CompareChart';
import { Badge } from '../components/ui/Badge';
import { PageHeader } from '../components/ui/PageHeader';
import { compareColor } from '../lib/chartColors';
import { saveBlob, saveText } from '../lib/chartExport';
import { compareRuns, configDifferences } from '../lib/compare';
import { formatDuration } from '../lib/diagramLayout';
import { csvCell } from '../lib/exportRun';
import { EXPERIMENT_STATUS } from '../lib/labels';
import type { Experiment } from '../types/experiment';
import type { Generation } from '../types/generation';

const MAX_RUNS = 5;
const SETTING_LABELS: Record<string, string> = {
  alpha: 'Alpha',
  sigma: 'Sigma',
  task: 'Workload',
  modelName: 'Model',
  schedulerPolicy: 'Scheduling policy',
  syncMode: 'Sync mode',
  candidatesPerGeneration: 'Candidates per generation',
  maxGenerations: 'Maximum generations',
  decodeEngine: 'Decoder',
  workerIds: 'Workers',
  recipeVersion: 'Recipe',
  batchSize: 'Batch size',
  sigmaSchedule: 'Sigma schedule',
  sigmaMinimum: 'Minimum sigma',
  maxNewTokens: 'Maximum output tokens',
  weightSpace: 'Weight space',
  antithetic: 'Antithetic sampling',
  scorer: 'Declarative scorer',
  coefficientRule: 'Coefficient rule',
  systemPrompt: 'System prompt',
  alphaSchedule: 'Alpha schedule',
  alphaMinimum: 'Minimum alpha',
  momentumBeta: 'Momentum beta',
  momentumWindow: 'Momentum window',
  evalChunk: 'Prompts per generation call',
  sampler: 'Batch sampler',
};

export function ComparePage() {
  const { t } = useProduct();
  const scope = useScopeKey();
  const [params] = useSearchParams();
  const ids = useMemo(
    () => [...new Set((params.get('ids') ?? '').split(',').filter(Boolean))].slice(0, MAX_RUNS),
    [params],
  );
  const svg = useRef<SVGSVGElement>(null);
  const loaded = useQueries({
    queries: ids.flatMap((id) => [
      {
        queryKey: ['experiment', id, ...scope],
        queryFn: () => apiGet<Experiment>(`/api/v1/experiments/${encodeURIComponent(id)}`),
        enabled: scope.every(Boolean),
        refetchInterval: 5000,
      },
      {
        queryKey: ['generations', id, ...scope],
        queryFn: () => apiGet<Generation[]>(`/api/v1/experiments/${encodeURIComponent(id)}/generations`),
        enabled: scope.every(Boolean),
        refetchInterval: 5000,
      },
    ]),
  });
  const pairs = ids.map((id, index) => ({
    id,
    experiment: loaded[index * 2].data as Experiment | undefined,
    generations: (loaded[index * 2 + 1].data as Generation[] | undefined) ?? [],
    failed: loaded[index * 2].isError,
  }));
  const ready = pairs.filter((p): p is typeof p & { experiment: Experiment } => Boolean(p.experiment));
  const result = compareRuns(ready.map((p) => ({ experiment: p.experiment, generations: p.generations })));
  const differences = configDifferences(ready.map((p) => p.experiment));

  if (ids.length < 2)
    return (
      <>
        <PageHeader title={t('Compare experiments')} />
        <EmptyState
          title={t('Pick at least two experiments')}
          message="Select experiments in the list and choose Compare."
        >
          <Link className="btn pri" to="/experiments">
            {t('Experiments')}
          </Link>
        </EmptyState>
      </>
    );
  if (loaded.some((query) => query.isPending) && !ready.length) return <LoadingState />;

  const csv = () => {
    const header = [
      'run',
      'status',
      'best_reward',
      'last_mean_reward',
      'duration_seconds',
      'gpus',
      'completed_generations',
    ].join(',');
    saveText(
      [
        header,
        ...result.rows.map((r) =>
          [r.name, r.status, r.bestReward, r.lastMean, r.durationSeconds, r.workers.join(' '), r.completedGenerations]
            .map(csvCell)
            .join(','),
        ),
      ].join('\n') + '\n',
      'comparison.csv',
      'text/csv',
    );
  };
  const png = async () => {
    if (!svg.current) return;
    const { svgToPngBlob } = await import('../lib/chartExport');
    saveBlob(await svgToPngBlob(svg.current), 'comparison-reward.png');
  };

  return (
    <>
      <PageHeader
        title={t('Compare experiments')}
        description={t('Mean reward (solid) and best reward (dashed) per generation, side by side.')}
        actions={
          <>
            <Link className="btn" to="/experiments">
              ← {t('Experiments')}
            </Link>
            <button type="button" className="btn" onClick={csv}>
              {t('Table (CSV)')}
            </button>
            <button type="button" className="btn" onClick={() => void png()}>
              {t('Chart (PNG)')}
            </button>
          </>
        }
      />
      {pairs.some((p) => p.failed) && (
        <p className="note err" role="alert">
          {t('Some experiments could not be loaded.')}
        </p>
      )}
      <section className="card">
        <div className="cb">
          {result.mixedWeightSpaces ? (
            <p className="note">{t('Runs with different weight spaces use separate reward charts.')}</p>
          ) : result.series.some((s) => s.points.length) ? (
            <CompareChart
              series={result.series}
              maxGeneration={result.maxGeneration}
              maxReward={result.maxReward}
              svgRef={svg}
            />
          ) : (
            <EmptyState
              title={t('No reward data yet')}
              message="Reward appears once a generation has an accepted candidate."
            />
          )}
          <ul className="compare-legend">
            {ready.map((p, index) => (
              <li key={p.experiment.experimentId}>
                <i style={{ background: compareColor(index) }} />
                <Link to={`/experiments/${p.experiment.experimentId}`}>{p.experiment.name}</Link>
              </li>
            ))}
          </ul>
        </div>
      </section>
      <section className="card">
        <div className="ch">
          <h2>{t('Results')}</h2>
        </div>
        <div className="scroll">
          <table className="lv-table">
            <thead>
              <tr>
                <th scope="col">{t('Experiment')}</th>
                <th scope="col">{t('Status')}</th>
                <th scope="col">{t('Best reward')}</th>
                <th scope="col">{t('Latest mean reward')}</th>
                <th scope="col">{t('Duration')}</th>
                <th scope="col">{t('Generations done')}</th>
                <th scope="col">{t('GPUs')}</th>
              </tr>
            </thead>
            <tbody>
              {result.rows.map((row, index) => {
                const best = Math.max(...result.rows.map((r) => r.bestReward ?? -Infinity));
                const fastest = Math.min(...result.rows.map((r) => r.durationSeconds ?? Infinity));
                return (
                  <tr key={row.id}>
                    <th scope="row">
                      <i className="compare-dot" style={{ background: compareColor(index) }} /> {row.name}
                    </th>
                    <td>
                      <Badge info={EXPERIMENT_STATUS[row.status as keyof typeof EXPERIMENT_STATUS]} />
                    </td>
                    <td className={row.bestReward === best && result.rows.length > 1 ? 'compare-win' : ''}>
                      {row.bestReward?.toFixed(4) ?? '—'}
                    </td>
                    <td>{row.lastMean?.toFixed(4) ?? '—'}</td>
                    <td className={row.durationSeconds === fastest && result.rows.length > 1 ? 'compare-win' : ''}>
                      {row.durationSeconds === null ? '—' : formatDuration(row.durationSeconds * 1000)}
                    </td>
                    <td>{row.completedGenerations}</td>
                    <td>{row.workers.join(', ') || '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
      <section className="card">
        <div className="ch">
          <h2>{t('What was different')}</h2>
        </div>
        <div className="cb">
          {differences.length === 0 ? (
            <p className="hint">{t('These experiments used the same settings.')}</p>
          ) : (
            <div className="scroll">
              <table className="lv-table">
                <thead>
                  <tr>
                    <th scope="col">{t('Setting')}</th>
                    {ready.map((p, index) => (
                      <th scope="col" key={p.experiment.experimentId}>
                        <i className="compare-dot" style={{ background: compareColor(index) }} /> {p.experiment.name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {differences.map((d) => (
                    <tr key={d.key}>
                      <th scope="row">{t(SETTING_LABELS[d.key] ?? d.key)}</th>
                      {d.values.map((v, i) => (
                        <td key={i}>{v}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </>
  );
}
