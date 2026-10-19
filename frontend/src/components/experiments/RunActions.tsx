import { useProduct } from '@heteroes/product-ui';
import { useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { useAppState } from '../../app/appState';
import { useTemplateMutations } from '../../hooks/useTemplates';
import { fileStem, saveText } from '../../lib/chartExport';
import { generationsCsv, summaryMarkdown } from '../../lib/exportRun';
import { templateConfigFromExperiment } from '../../lib/templates';
import type { Experiment } from '../../types/experiment';
import type { Generation } from '../../types/generation';
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
