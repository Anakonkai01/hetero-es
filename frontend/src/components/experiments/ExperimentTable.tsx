import { useProduct } from '@heteroes/product-ui';
import { Link } from 'react-router';
import { formatDateTime, shortId } from '../../lib/format';
import { EXPERIMENT_STATUS } from '../../lib/labels';
import type { BackState } from '../../lib/navigation';
import type { Experiment } from '../../types/experiment';
import { Badge } from '../ui/Badge';
import { CurrentGenerationProgress } from './CurrentGenerationProgress';

interface ExperimentTableProps {
  experiments: Experiment[];
  /** The compact variant is used on the dashboard. */
  compact?: boolean;
  backState?: BackState;
  /** Selection for comparing runs: the chosen ids and a toggle. */
  picked?: string[];
  onPick?: (id: string) => void;
}

export function ExperimentTable({ experiments, compact, backState, picked, onPick }: ExperimentTableProps) {
  const { t } = useProduct();
  const columns = compact ? 'cols-dexp' : 'cols-exp';

  return (
    <div className="scroll">
      <div
        className={compact ? 'tw s' : 'tw'}
        role="table"
        aria-label={compact ? t('Recent experiments') : t('Experiments')}
      >
        <div className={`rowh ${columns}`} role="row">
          <div className="c" role="columnheader">
            {compact ? t('Experiment') : t('Name')}
          </div>
          <div className="c" role="columnheader">
            {t('Status')}
          </div>
          <div className="c" role="columnheader">
            {t('Model')}
          </div>
          {!compact && (
            <div className="c" role="columnheader">
              {t('Scheduling policy')}
            </div>
          )}
          <div className="c" role="columnheader">
            {compact ? t('Current generation progress') : t('Current generation')}
          </div>
          {!compact && (
            <div className="c" role="columnheader">
              {t('Created')}
            </div>
          )}
        </div>

        {experiments.map((experiment) => (
          <div className={`row ${columns}`} role="row" key={experiment.experimentId}>
            <div className="c" role="cell">
              {onPick && (
                <label className="compare-pick">
                  <input
                    type="checkbox"
                    checked={picked?.includes(experiment.experimentId) ?? false}
                    onChange={() => onPick(experiment.experimentId)}
                    aria-label={`${t('Select for comparison')}: ${experiment.name}`}
                  />
                </label>
              )}
              <Link
                className="link"
                style={{
                  fontWeight: 500,
                  color: 'var(--ink)',
                  whiteSpace: compact ? undefined : 'normal',
                }}
                to={`/experiments/${experiment.experimentId}`}
                state={backState}
              >
                {experiment.name}
              </Link>
              <div className="mono mut">{shortId(experiment.experimentId)}</div>
            </div>

            <div className="c" role="cell">
              <Badge info={EXPERIMENT_STATUS[experiment.status]} />
              {!compact && experiment.cancelRequested && experiment.status === 'RUNNING' && (
                <div className="hint">{t('Cancel requested')}</div>
              )}
            </div>

            <div className="c" role="cell">
              {experiment.modelName}
            </div>

            {!compact && (
              <div className="c mono" role="cell">
                {experiment.schedulerPolicy}
              </div>
            )}

            <div className="c" role="cell">
              <CurrentGenerationProgress experiment={experiment} linkGeneration={compact} />
            </div>

            {!compact && (
              <div className="c mut" role="cell">
                {formatDateTime(experiment.createdAt)}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
