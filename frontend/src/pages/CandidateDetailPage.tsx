import { useProduct } from '@heteroes/product-ui';
import { Link, useParams } from 'react-router';
import { isNotFoundError, isServerError } from '../api/client';
import { useAppState } from '../app/appState';
import { EmptyState } from '../components/common/EmptyState';
import { ErrorState } from '../components/common/ErrorState';
import { ObjectNotFound } from '../components/common/ObjectNotFound';
import { QueryState } from '../components/common/QueryState';
import { EventRows } from '../components/events/EventRows';
import { Badge } from '../components/ui/Badge';
import { Breadcrumbs } from '../components/ui/Breadcrumbs';
import { CopyButton } from '../components/ui/CopyButton';
import { KeyValue } from '../components/ui/KeyValue';
import { PageHeader, PageHeaderMeta } from '../components/ui/PageHeader';
import { useAttempt } from '../hooks/useAttempt';
import { useCandidate } from '../hooks/useCandidate';
import { useEvents } from '../hooks/useEvents';
import { useExperiment } from '../hooks/useExperiment';
import { NOT_AVAILABLE, formatClock, formatDateTime, shortId } from '../lib/format';
import { ATTEMPT_STATUS, CANDIDATE_STATUS } from '../lib/labels';

export function CandidateDetailPage() {
  const { t } = useProduct();
  const { experimentId = '', generationId = '', candidateId = '' } = useParams();
  const { retryRegion } = useAppState();

  const experimentQuery = useExperiment(experimentId);
  const candidateQuery = useCandidate(candidateId);
  const attemptQuery = useAttempt(candidateQuery.data?.attemptId);
  const eventsQuery = useEvents();

  if (isNotFoundError(candidateQuery.error) || isNotFoundError(experimentQuery.error)) {
    return <ObjectNotFound backTo="/experiments" backLabel="Back to Experiments" />;
  }

  const candidate = candidateQuery.data;
  const attempt = attemptQuery.data;
  const events = (eventsQuery.data ?? []).filter((event) => event.candidateId === candidateId);
  const attemptFailed = attemptQuery.isError && isServerError(attemptQuery.error);
  const backToGeneration = `/experiments/${experimentId}/generations/${generationId}`;
  const status = candidate ? CANDIDATE_STATUS[candidate.status] : undefined;

  return (
    <QueryState
      isPending={candidateQuery.isPending}
      isError={candidateQuery.isError}
      hasData={Boolean(candidate)}
      title={t('Could not load the candidate')}
    >
      {candidate && status && (
        <>
          <Breadcrumbs
            crumbs={[
              { label: 'Experiments', to: '/experiments' },
              {
                label: experimentQuery.data?.name ?? shortId(experimentId),
                title: experimentId,
                to: `/experiments/${experimentId}`,
              },
              {
                label: `Generation ${shortId(generationId)}`,
                title: generationId,
                to: backToGeneration,
              },
              {
                label: `Candidate ${shortId(candidateId)}`,
                title: candidateId,
              },
            ]}
          />

          <PageHeader
            title={
              <>
                {t('Candidate')}{' '}
                <span className="mono" style={{ fontSize: 20 }}>
                  {shortId(candidateId)}
                </span>
              </>
            }
            meta={
              <PageHeaderMeta>
                <Badge info={status} />
                <span className="mono">{candidateId}</span>
                <CopyButton value={candidateId} subject="candidate" />
              </PageHeaderMeta>
            }
            actions={
              <Link className="btn" to={backToGeneration}>
                {t('← Back to generation')}
              </Link>
            }
          />

          <div className="note">
            <b>{candidate.status}:</b> {status.title}
            {t(
              '. A worker finishing its computation does not mean the result was accepted; only COMMITTED means accepted by the system.',
            )}
          </div>

          <section className="card">
            <div className="cb" style={{ paddingTop: 20 }}>
              <dl className="kv">
                <KeyValue label={t('Model version')} mono>
                  {candidate.modelVersion}
                </KeyValue>
                <KeyValue label={t('Assigned worker')}>
                  {candidate.workerId ? (
                    <Link className="link mono" to={`/workers/${candidate.workerId}`}>
                      {candidate.workerId}
                    </Link>
                  ) : (
                    <span className="mut">{t('Not assigned')}</span>
                  )}
                </KeyValue>
                <KeyValue label={t('Seed')} mono>
                  {candidate.seed}
                </KeyValue>
                <KeyValue label={t('Reward')} mono>
                  {candidate.reward?.toFixed(3) ?? NOT_AVAILABLE}
                </KeyValue>
                <KeyValue label={t('Generation')}>
                  <Link className="link mono" to={backToGeneration}>
                    {shortId(generationId)}
                  </Link>
                </KeyValue>
              </dl>
            </div>

            <details style={{ borderTop: '1px solid var(--line2)' }}>
              <summary>{t('Technical details')}</summary>
              <div className="cb" style={{ paddingTop: 0 }}>
                <dl className="kv">
                  <KeyValue label={t('Seed')} mono>
                    {candidate.seed}
                  </KeyValue>
                  <KeyValue label={t('Batch IDs')} mono>
                    {candidate.batchIds.join(', ')}
                  </KeyValue>
                  <KeyValue label={t('Config hash')} mono>
                    {candidate.generationConfigHash}
                  </KeyValue>
                  <KeyValue label={t('Lease deadline (GMT+7)')} mono>
                    {candidate.leaseDeadline ? formatDateTime(candidate.leaseDeadline) : NOT_AVAILABLE}
                  </KeyValue>
                </dl>
              </div>
            </details>
          </section>

          <section className="card" aria-label={t('Attempt')}>
            <div className="ch">
              <h2>{t('Attempt')}</h2>
              <small>
                {t(
                  'An attempt is one execution of the candidate on a worker. Showing the latest attempt the system provides.',
                )}
              </small>
            </div>

            {attemptFailed ? (
              <ErrorState
                title={t('Could not load the attempt')}
                message="The candidate information above is still readable."
                onRetry={retryRegion}
              />
            ) : !candidate.attemptId ? (
              <EmptyState title={t('Not started')} message="This candidate has no attempt yet." />
            ) : attempt ? (
              <>
                <div className="scroll">
                  <div className="tw s" role="table" aria-label={t('Attempt')}>
                    <div className="rowh cols-att" role="row">
                      <div className="c" role="columnheader">
                        {t('Attempt')}
                      </div>
                      <div className="c" role="columnheader">
                        {t('Worker')}
                      </div>
                      <div className="c" role="columnheader">
                        {t('Status')}
                      </div>
                      <div className="c" role="columnheader">
                        {t('Started')}
                      </div>
                      <div className="c" role="columnheader">
                        {t('Ended')}
                      </div>
                      <div className="c" role="columnheader">
                        {t('Error kind')}
                      </div>
                    </div>
                    <div className={attempt.status === 'FAILED' ? 'row cols-att sel' : 'row cols-att'} role="row">
                      <div className="c mono" role="cell" title={attempt.attemptId}>
                        {shortId(attempt.attemptId)}
                      </div>
                      <div className="c" role="cell">
                        <Link className="link mono" to={`/workers/${attempt.workerId}`}>
                          {attempt.workerId}
                        </Link>
                      </div>
                      <div className="c" role="cell">
                        <Badge info={ATTEMPT_STATUS[attempt.status]} title="" />
                      </div>
                      <div className="c mono" role="cell">
                        {formatClock(attempt.startedAt)}
                      </div>
                      <div className="c mono" role="cell">
                        {attempt.completedAt ? formatClock(attempt.completedAt) : t('—')}
                      </div>
                      <div className="c mono" role="cell">
                        {attempt.errorType ?? '—'}
                      </div>
                    </div>
                  </div>
                </div>

                {attempt.status === 'FAILED' && (
                  <div className="cb" style={{ paddingTop: 12 }}>
                    <div className="note err">
                      <b>{t('The attempt failed.')}</b> {t('The candidate remains')} {candidate.status}{' '}
                      {t(
                        'and is waiting to be reassigned. Only one attempt is provided by the system; there is no multi-attempt history yet.',
                      )}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <EmptyState title={t('Loading the attempt…')} />
            )}
          </section>

          <section className="card" aria-label={t('Related events')}>
            <div className="ch">
              <h2>{t('Related events')}</h2>
            </div>
            {events.length === 0 ? (
              <EmptyState title={t('No related events')} />
            ) : (
              <EventRows events={events} label={t('Related events')} />
            )}
          </section>
        </>
      )}
    </QueryState>
  );
}
