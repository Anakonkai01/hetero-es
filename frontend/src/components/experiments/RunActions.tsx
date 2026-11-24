import { useProduct } from '@heteroes/product-ui';
import { useQuery } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { apiGet } from '../../api/client';
import { useAppState } from '../../app/appState';
import { useScopeKey } from '../../app/session';
import { useTemplateMutations } from '../../hooks/useTemplates';
import { fileStem, saveText } from '../../lib/chartExport';
import { generationsCsv, summaryMarkdown } from '../../lib/exportRun';
import { templateConfigFromExperiment } from '../../lib/templates';
import type { Experiment } from '../../types/experiment';
import type { Generation } from '../../types/generation';

interface RecoveryPoint {
  pointId: string;
  generation: number;
  final: boolean;
  status: string;
}

/** The things you do with a run once you have seen it: run it again, keep its settings, export it for a report. */
export function RunActions({
  experiment,
  generations,
  chart,
}: {
  experiment: Experiment;
  generations: Generation[];
  chart?: () => SVGSVGElement | null;
}) {
  const { t } = useProduct();
  const navigate = useNavigate();
  const { flash } = useAppState();
  const { create } = useTemplateMutations();
  const scope = useScopeKey();
  const [choosingPoint, setChoosingPoint] = useState(false);
  const runId = experiment.experimentId;
  const canContinue = experiment.recipeVersion === 3 && ['full', 'subset'].includes(experiment.weightSpace?.kind ?? '');
  const checkpoints = useQuery({
    queryKey: ['recovery-points', runId, ...scope],
    queryFn: () => apiGet<RecoveryPoint[]>(`/api/v1/experiments/${encodeURIComponent(runId)}/recovery-points`),
    enabled: canContinue && choosingPoint && scope.every(Boolean),
  });
  const ready = (checkpoints.data ?? []).filter((point) => point.status === 'READY');
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const input = useRef<HTMLInputElement>(null);
  const stem = fileStem(experiment.name);
  async function png() {
    const svg = chart?.();
    if (!svg) {
      flash(t('Open the Overview tab to export its chart.'));
      return;
    }
    try {
      const { svgToPngBlob, saveBlob } = await import('../../lib/chartExport');
      saveBlob(await svgToPngBlob(svg), `${stem}-reward.png`);
    } catch {
      flash(t('Could not create the image.'));
    }
  }
  return (
    <div className="run-actions">
      {
        <button
          type="button"
          className="btn"
          onClick={() => navigate('/experiments/new', { state: { clone: experiment } })}
        >
          ↻ {t('Run again like this')}
        </button>
      }
      {canContinue && (
        <details className="export-menu" onToggle={(event) => setChoosingPoint(event.currentTarget.open)}>
          <summary className="btn">{t('Continue from checkpoint')} ▾</summary>
          <div>
            {checkpoints.isFetching && <p className="hint">{t('Loading…')}</p>}
            {!checkpoints.isFetching && checkpoints.isError && (
              <p className="note err" role="alert">
                {t('Could not load checkpoints')}
              </p>
            )}
            {!checkpoints.isFetching && !checkpoints.isError && !ready.length && (
              <p className="hint">{t('No verified checkpoints')}</p>
            )}
            {ready.map((point) => (
              <button
                key={point.pointId}
                type="button"
                onClick={() =>
                  navigate('/experiments/new', {
                    state: {
                      clone: experiment,
                      continueFrom: { runId, pointId: point.pointId, generation: point.generation },
                    },
                  })
                }
              >
                {t('Generation')} {point.generation + 1}
                {point.final ? ` · ${t('Final checkpoint')}` : ''}
              </button>
            ))}
          </div>
        </details>
      )}
      {
        <button
          type="button"
          className="btn"
          onClick={() => {
            setNaming(true);
            setName(experiment.name);
            setError('');
            setTimeout(() => input.current?.select(), 0);
          }}
        >
          {t('Save settings as template')}
        </button>
      }
      <details className="export-menu">
        <summary className="btn">{t('Export')} ▾</summary>
        <div
          role="menu"
          onClick={(event) => {
            (event.currentTarget.closest('details') as HTMLDetailsElement).open = false;
          }}
        >
          <button
            type="button"
            role="menuitem"
            onClick={() => saveText(generationsCsv(experiment, generations), `${stem}-generations.csv`, 'text/csv')}
          >
            {t('Generations (CSV)')}
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => saveText(summaryMarkdown(experiment, generations), `${stem}-summary.md`, 'text/markdown')}
          >
            {t('One-page summary (Markdown)')}
          </button>
          <button type="button" role="menuitem" onClick={() => void png()}>
            {t('Reward chart (PNG)')}
          </button>
        </div>
      </details>
      {naming && (
        <form
          className="template-name"
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate(
              { name, config: templateConfigFromExperiment(experiment) },
              {
                onSuccess: () => {
                  setNaming(false);
                  flash(t('Template saved.'));
                },
                onError: (e: Error) => setError(e.message),
              },
            );
          }}
        >
          <label className="fg">
            {t('Template name')}
            <input
              ref={input}
              className="inp"
              required
              minLength={3}
              maxLength={100}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <button className="btn pri" disabled={create.isPending}>
            {t('Save')}
          </button>
          <button type="button" className="btn" onClick={() => setNaming(false)}>
            {t('Cancel')}
          </button>
          {error && (
            <p className="note err" role="alert">
              {error}
            </p>
          )}
        </form>
      )}
    </div>
  );
}
