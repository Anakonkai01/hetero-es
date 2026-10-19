import { useProduct } from '@heteroes/product-ui';
import { useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router';
import { isNotFoundError, isServerError } from '../api/client';
import { useAppState } from '../app/appState';
import { EmptyState } from '../components/common/EmptyState';
import { ErrorState } from '../components/common/ErrorState';
import { ObjectNotFound } from '../components/common/ObjectNotFound';
import { QueryState } from '../components/common/QueryState';
import { EventRows } from '../components/events/EventRows';
import { CancelDialog } from '../components/experiments/CancelDialog';
import { ExperimentControls } from '../components/experiments/ExperimentControls';
import { ExperimentResults } from '../components/experiments/ExperimentResults';
import { RunActions } from '../components/experiments/RunActions';
import { ExperimentLive } from '../components/live/ExperimentLive';
import { Badge } from '../components/ui/Badge';
import { Breadcrumbs } from '../components/ui/Breadcrumbs';
import { CopyButton } from '../components/ui/CopyButton';
import { KeyValue } from '../components/ui/KeyValue';
import { PageHeader, PageHeaderMeta } from '../components/ui/PageHeader';
import { ProgressBar } from '../components/ui/ProgressBar';
import { useArtifacts } from '../hooks/useArtifacts';
import { useEvents } from '../hooks/useEvents';
import { useExperiment } from '../hooks/useExperiment';
import { useGenerations } from '../hooks/useGenerations';
import { formatDateTime, formatOptionalDateTime, formatReward, shortId } from '../lib/format';
import { ARTIFACT_STATUS, ARTIFACT_TYPE_LABEL, EXPERIMENT_STATUS } from '../lib/labels';
import { useBackState } from '../lib/navigation';
type Tab = 'overview' | 'live' | 'generations' | 'config' | 'events' | 'artifacts';
const tabs: {
  id: Tab;
  label: string;
}[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'live', label: 'Live and replay' },
  { id: 'generations', label: 'Generations' },
  { id: 'config', label: 'Configuration' },
  { id: 'events', label: 'Logs' },
  { id: 'artifacts', label: 'Results & saved model' },
];
export function ExperimentDetailPage() {
  const { t } = useProduct();
  const { experimentId = '' } = useParams();
  const { retryRegion } = useAppState();
  const back = useBackState();
  const requested = useSearchParams()[0].get('tab');
  const [tab, setTab] = useState<Tab>(tabs.some((item) => item.id === requested) ? (requested as Tab) : 'overview');
  const [cancelOpen, setCancelOpen] = useState(false);
  const experimentQuery = useExperiment(experimentId);
  const generationsQuery = useGenerations(experimentId);
  const eventsQuery = useEvents();
  const artifactsQuery = useArtifacts();
  if (isNotFoundError(experimentQuery.error)) {
    return <ObjectNotFound backTo="/experiments" backLabel="Back to Experiments" />;
  }
  const experiment = experimentQuery.data;
  const generations = generationsQuery.data ?? [];
  const events = (eventsQuery.data ?? []).filter((e) => e.experimentId === experimentId);
  const artifacts = (artifactsQuery.data ?? []).filter((a) => a.experimentId === experimentId);
  const currentGeneration = generations.find((g) => g.generationId === experiment?.currentGenerationId);
  const eventsFailed = eventsQuery.isError && isServerError(eventsQuery.error);
  return (
    <QueryState
      isPending={experimentQuery.isPending}
      isError={experimentQuery.isError}
      hasData={Boolean(experiment)}
      title={t('Could not load the experiment')}
    >
      {experiment && (
        <>
          <Breadcrumbs
            crumbs={[
              { label: 'Experiments', to: '/experiments' },
              { label: experiment.name, title: experiment.experimentId },
            ]}
          />

          <PageHeader
            title={experiment.name}
            meta={
              <>
                <PageHeaderMeta>
                  <Badge info={EXPERIMENT_STATUS[experiment.status]} />
                  <span className="mono tech" title={experiment.experimentId}>
                    {shortId(experiment.experimentId)}
                  </span>
                  <span className="tech">
                    <CopyButton value={experiment.experimentId} subject="experiment" />
                  </span>
                  <span>
                    {experiment.modelName}{' '}
                    <span className="tech">
                      ·{' '}
                      <span className="mono" title={experiment.modelVersion}>
                        {shortId(experiment.modelVersion)}
                      </span>
                    </span>
                  </span>
                </PageHeaderMeta>
                {experiment.cancelRequested && experiment.status === 'RUNNING' && (
                  <p style={{ margin: '6px 0 0' }}>
                    <Badge tone="warn" label={t('Cancel request received')} />{' '}
                    <span className="hint">
                      {t('The official status stays')} {EXPERIMENT_STATUS[experiment.status].label}{' '}
                      {t('until the coordinator confirms.')}
                    </span>
                  </p>
                )}
              </>
            }
            actions={
              <>
                {back && (
                  <Link className="btn" to={back.backTo}>
                    {t('← Back to')}
                    {back.backLabel}
                  </Link>
                )}
                {!experiment.maxGenerations &&
                  ['RUNNING', 'QUEUED'].includes(experiment.status) &&
                  !experiment.cancelRequested && (
                    <button type="button" className="btn dng" onClick={() => setCancelOpen(true)}>
                      {t('Request cancel')}
                    </button>
                  )}
              </>
            }
          />

          <RunActions
            experiment={experiment}
            generations={generations}
            chart={() => document.querySelector<SVGSVGElement>('svg.reward-chart')}
          />

          <ExperimentControls key={`${experiment.experimentId}:${experiment.status}`} experiment={experiment} />

          <div role="tablist" className="tabs" aria-label={t('Experiment sections')}>
            {tabs.map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                className={tab === item.id ? 'tab on' : 'tab'}
                aria-selected={tab === item.id}
                onClick={() => setTab(item.id)}
              >
                {t(item.label)}
              </button>
            ))}
          </div>

          {tab === 'overview' && (
            <>
              <ExperimentResults experiment={experiment} />
              <section className="card" aria-label={t('Summary')}>
                <div className="cb" style={{ paddingTop: 20 }}>
                  <dl className="kv">
                    <KeyValue label={t('Scheduling policy')} mono>
                      {experiment.schedulerPolicy}
                    </KeyValue>
                    <KeyValue label={t('Sync mode')} mono>
                      {experiment.syncMode}
                    </KeyValue>
                    <KeyValue label={t('Created')}>{formatDateTime(experiment.createdAt)}</KeyValue>
                    <KeyValue label={t('Started')}>
                      {formatOptionalDateTime(experiment.startedAt, 'Not available yet')}
                    </KeyValue>
                    <KeyValue label={t('Ended')}>
                      {formatOptionalDateTime(experiment.completedAt, 'Not ended')}
                    </KeyValue>
                    <KeyValue label={t('Current generation')}>
                      {currentGeneration ? (
                        <Link
                          className="link mono"
                          to={`/experiments/${experimentId}/generations/${currentGeneration.generationId}`}
                        >
                          {shortId(currentGeneration.generationId)}
                        </Link>
                      ) : (
                        <span className="mut">{t('Not available yet')}</span>
                      )}
                    </KeyValue>
                  </dl>
                </div>
              </section>

              <section className="card" aria-label={t('Current generation progress')}>
                <div className="ch">
                  <h2>{t('Current generation progress')}</h2>
                  <small>{t('Counts only candidates of the running generation, not the whole experiment.')}</small>
                </div>
                <div className="cb">
                  {currentGeneration ? (
                    <div className="prog">
                      <span>
                        <b
                          style={{
                            color: 'var(--ink)',
                            fontSize: 20,
                            fontWeight: 500,
                          }}
                        >
                          {currentGeneration.committedCandidateCount} / {currentGeneration.candidateCount}
                        </b>{' '}
                        {t('candidates COMMITTED')}
                      </span>
                      <ProgressBar
                        large
                        done={currentGeneration.committedCandidateCount}
                        total={currentGeneration.candidateCount}
                      />
                      <span>
                        {experiment.maxGenerations
                          ? `Completed generations: ${experiment.completedGenerations ?? 0} / ${experiment.maxGenerations}`
                          : t('Legacy fixture: no generation limit recorded.')}
                      </span>
                    </div>
                  ) : (
                    <span className="mut">{t('No generation is running.')}</span>
                  )}
                </div>
              </section>
            </>
          )}

          {tab === 'live' && <ExperimentLive experimentId={experiment.experimentId} status={experiment.status} />}

          {tab === 'generations' && (
            <section className="card" aria-label={t('Generations')}>
              {generations.length === 0 ? (
                <EmptyState
                  title={t('No generations yet')}
                  message="The first generation appears after the coordinator confirms the experiment has started."
                />
              ) : (
                <div className="scroll">
                  <div className="tw" role="table" aria-label={t('Generations')}>
                    <div className="rowh cols-gen" role="row" style={{ marginTop: 8 }}>
                      <div className="c" role="columnheader">
                        {t('Generation')}
                      </div>
                      <div className="c" role="columnheader">
                        {t('Status')}
                      </div>
                      <div className="c" role="columnheader">
                        {t('Model version')}
                      </div>
                      <div className="c" role="columnheader">
                        {t('Candidates COMMITTED')}
                      </div>
                      <div className="c" role="columnheader">
                        {t('Mean reward')}
                      </div>
                      <div className="c" role="columnheader">
                        {t('Best reward')}
                      </div>
                      <div className="c" role="columnheader">
                        {t('Started')}
                      </div>
                    </div>
                    {generations.map((generation) => (
                      <div className="row cols-gen" role="row" key={generation.generationId}>
                        <div className="c" role="cell">
                          <Link
                            className="link mono"
                            title={generation.generationId}
                            to={`/experiments/${experimentId}/generations/${generation.generationId}`}
                          >
                            {shortId(generation.generationId)}
                          </Link>
                        </div>
                        <div className="c" role="cell">
                          <Badge info={EXPERIMENT_STATUS[generation.status]} />
                        </div>
                        <div className="c mono" role="cell">
                          {generation.modelVersion}
                        </div>
                        <div className="c" role="cell">
                          <div className="prog">
                            <span>
                              {generation.committedCandidateCount} / {generation.candidateCount}
                            </span>
                            <ProgressBar done={generation.committedCandidateCount} total={generation.candidateCount} />
                          </div>
                        </div>
                        <div className="c mono" role="cell">
                          {formatReward(generation.rewardMean)}
                        </div>
                        <div className="c mono" role="cell">
                          {formatReward(generation.rewardBest)}
                        </div>
                        <div className="c mut" role="cell">
                          {formatDateTime(generation.startedAt)}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </section>
          )}

          {tab === 'config' && (
            <section className="card" aria-label={t('Configuration')}>
              <div className="ch">
                <h2>{t('Experiment configuration')}</h2>
                <small>{t('Read-only. Training configuration is fixed after submission.')}</small>
              </div>
              <div className="cb">
                <dl className="kv">
                  <KeyValue label={t('Model')}>{experiment.modelName}</KeyValue>
                  <KeyValue label={t('Task')}>{experiment.task}</KeyValue>
                  {experiment.recipeVersion === 3 && (
                    <>
                      <KeyValue label={t('Weight space')}>{experiment.weightSpace?.kind}</KeyValue>
                      <KeyValue label={t('Declarative scorer')}>
                        {experiment.scorer?.name}@{experiment.scorer?.version}
                      </KeyValue>
                      <KeyValue label={t('Antithetic sampling')}>{t(experiment.antithetic ? 'ON' : 'OFF')}</KeyValue>
                      <KeyValue label={t('Coefficient rule')}>{experiment.coefficientRule}</KeyValue>
                    </>
                  )}
                  <KeyValue label={t('Maximum generations')}>{experiment.maxGenerations ?? 'Legacy fixture'}</KeyValue>
                  {(experiment.recipeVersion ?? 1) === 1 && (
                    <KeyValue label={t('Built-in workload')}>{experiment.task}</KeyValue>
                  )}
                  <KeyValue label={t('Candidates per generation')} mono>
                    {experiment.candidatesPerGeneration}
                  </KeyValue>
                  <KeyValue label={t('Scheduling policy')} mono>
                    {experiment.schedulerPolicy}
                  </KeyValue>
                  <KeyValue label={t('Sync mode')} mono>
                    {experiment.syncMode}
                  </KeyValue>
                  <KeyValue label={t('Base seed')} mono>
                    {experiment.baseSeed ?? 'Derived from run ID, generation and candidate index'}
                  </KeyValue>
                  <KeyValue label={t('Config hash')} mono>
                    {experiment.configHash}
                  </KeyValue>
                </dl>
              </div>
            </section>
          )}

          {tab === 'events' && (
            <section className="card" aria-label={t('Experiment events')}>
              <div className="ch">
                <h2>{t('Events for this experiment')}</h2>
              </div>
              {experiment.maxGenerations && (
                <div className="cb demo-form">
                  <p>
                    {t('Canonical runtime')} · {experiment.status}
                  </p>
                  <p>
                    {experiment.completedGenerations ?? 0} {t('generations committed · Model')}
                    {experiment.modelVersion}
                  </p>
                  {experiment.checkpointSavedAt && (
                    <p>
                      {t('Generation state saved at')}
                      {formatDateTime(experiment.checkpointSavedAt)}
                    </p>
                  )}
                  {experiment.cancelRequested && <p>{t('Cancellation requested; waiting for confirmation.')}</p>}
                </div>
              )}
              {eventsFailed ? (
                <ErrorState
                  title={t('Could not load events')}
                  message="The other tabs of this experiment are still readable."
                  onRetry={retryRegion}
                  retryLabel="Retry this region"
                />
              ) : events.length === 0 ? (
                <EmptyState title={t('No events for this experiment yet')} />
              ) : (
                <EventRows events={events} label={t('Experiment events')} />
              )}
            </section>
          )}

          {tab === 'artifacts' && (
            <section className="card" aria-label={t('Experiment artifacts')}>
              <div className="ch">
                <h2>{t('Saved files')}</h2>
              </div>
              {artifacts.length === 0 ? (
                <EmptyState title={t('No saved model files yet')} />
              ) : (
                <div className="scroll">
                  <div className="tw s" role="table" aria-label={t('Experiment artifacts')}>
                    {artifacts.map((artifact) => (
                      <div
                        className="row"
                        role="row"
                        key={artifact.artifactId}
                        style={{
                          gridTemplateColumns: 'minmax(200px,2fr) 140px 160px',
                        }}
                      >
                        <div className="c" role="cell">
                          {artifact.name}
                        </div>
                        <div className="c" role="cell">
                          {ARTIFACT_TYPE_LABEL[artifact.type]}
                        </div>
                        <div className="c" role="cell">
                          <Badge info={ARTIFACT_STATUS[artifact.status]} />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </section>
          )}

          {cancelOpen && <CancelDialog experiment={experiment} onClose={() => setCancelOpen(false)} />}
        </>
      )}
    </QueryState>
  );
}
