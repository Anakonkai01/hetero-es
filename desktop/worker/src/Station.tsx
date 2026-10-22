import { Status, useProduct } from '@heteroes/product-ui';
import type { ReactNode } from 'react';
import type { Gauge, StationView } from './station';

const BLOCKERS: Record<string, string> = {
  approval: 'Waiting for administrator approval.',
  agent: 'The local agent is not running yet.',
};

/** The compact "GPU station": one big switch, what the GPU is doing, three gauges; everything else folds into Advanced. */
export function Station({
  view,
  gauges,
  gpuName,
  vramGiB,
  deviceName,
  approval,
  busy,
  onToggle,
  children,
}: {
  view: StationView;
  gauges: Gauge[];
  gpuName: string;
  vramGiB: string;
  deviceName: string;
  approval: string;
  busy: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  const { t } = useProduct();
  const on = view.mode === 'ready' || view.mode === 'working';
  return (
    <>
      <section className={`station station-${view.mode}`} aria-label={t('GPU station')}>
        <div className="station-top">
          <div>
            <p className="eyebrow">{deviceName}</p>
            <h1 className="station-gpu">{gpuName}</h1>
            <p className="hint">{vramGiB}</p>
          </div>
          <Status value={approval} />
        </div>
        <div className="station-switch">
          <button
            type="button"
            className={`switch ${on ? 'on' : ''}`}
            role="switch"
            aria-checked={on}
            aria-label={t(view.toggle.label)}
            disabled={busy || view.toggle.disabled}
            onClick={onToggle}
          >
            <span className="switch-knob" aria-hidden="true" />
          </button>
          <div>
            <h2 className="station-headline">{t(view.headline)}</h2>
            <p>{t(view.blocker ? BLOCKERS[view.blocker] : view.detail)}</p>
          </div>
        </div>
        {view.mode === 'working' && (
          <div className="station-working" role="status">
            <span className="pulse" aria-hidden="true" />
            <div>
              <b>{t('Evaluating candidates for the lab')}</b>
              {view.assignments.map((a) => (
                <small key={a.id} className="mono">
                  {a.id}
                  {a.epoch !== undefined ? ` · ${t('Epoch')} ${a.epoch}` : ''}
                </small>
              ))}
            </div>
          </div>
        )}
        <div className="gauges" aria-label={t('GPU measurements')}>
          {gauges.map((g) => (
            <div key={g.key} className="gauge">
              <div className="gauge-head">
                <span>{t(g.label)}</span>
                <b>{g.text}</b>
              </div>
              <div
                className="gauge-bar"
                role="progressbar"
                aria-label={t(g.label)}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={g.percent ?? undefined}
              >
                <span style={{ width: `${g.percent ?? 0}%` }} data-unknown={g.percent === null} />
              </div>
            </div>
          ))}
        </div>
      </section>
      <details className="advanced-panel station-advanced">
        <summary>{t('Advanced: network, role, assignments and diagnostics')}</summary>
        {children}
      </details>
    </>
  );
}
