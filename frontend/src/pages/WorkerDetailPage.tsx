import { ResourceTelemetry, useProduct } from '@heteroes/product-ui';
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
import { KeyValue } from '../components/ui/KeyValue';
import { PageHeader, PageHeaderMeta } from '../components/ui/PageHeader';
import { WorkerActivityBadge } from '../components/ui/WorkerActivity';
import { useEvents } from '../hooks/useEvents';
import { useWorker } from '../hooks/useWorker';
import { NOT_AVAILABLE, formatClock, formatGb } from '../lib/format';
import { ADMISSION_STATUS } from '../lib/labels';
export function WorkerDetailPage() {
  const { t } = useProduct();
  const { workerId = '' } = useParams();
  const { retryRegion } = useAppState();
  const workerQuery = useWorker(workerId);
  const eventsQuery = useEvents();
  if (isNotFoundError(workerQuery.error)) {
    return <ObjectNotFound backTo="/workers" backLabel="Back to Workers" />;
  }
  const worker = workerQuery.data;
  const events = (eventsQuery.data ?? []).filter((event) => event.workerId === workerId);
  const eventsFailed = eventsQuery.isError && isServerError(eventsQuery.error);
  return (
    <QueryState
      isPending={workerQuery.isPending}
      isError={workerQuery.isError}
      hasData={Boolean(worker)}
      title={t('Could not load the worker')}
    >
      {worker && (
        <>
          <Breadcrumbs crumbs={[{ label: 'Workers', to: '/workers' }, { label: worker.workerId }]} />

          <PageHeader
            title={
              <span className="mono" style={{ fontSize: 22 }}>
                {worker.workerId}
              </span>
            }
            meta={
              <PageHeaderMeta>
                <WorkerActivityBadge status={worker.status} />
                <Badge
                  info={ADMISSION_STATUS[worker.admissionStatus]}
                  label={`Admission: ${ADMISSION_STATUS[worker.admissionStatus].label}`}
                />
                <span>{worker.profile.gpuName}</span>
              </PageHeaderMeta>
            }
            actions={
              <Link className="btn" to="/workers">
                {t('← Back to Workers')}
              </Link>
            }
          />

          <section className="card">
            <div className="cb">
              <ResourceTelemetry
                observation={worker.telemetry}
                history={worker.telemetryHistory}
                online={worker.status === 'ONLINE'}
              />
            </div>
          </section>
          <div className="two">
            <section className="card" aria-label={t('GPU profile')}>
              <div className="ch">
                <h2>{t('GPU profile')}</h2>
              </div>
              <div className="cb">
                <dl className="kv">
                  <KeyValue label={t('GPU')}>{worker.profile.gpuName}</KeyValue>
                  <KeyValue label={t('Total VRAM')}>{formatGb(worker.profile.vramTotalMb)}</KeyValue>

                  <KeyValue label={t('Qualification throughput')}>
                    {worker.profile.throughputTokensPerSecond === undefined
                      ? NOT_AVAILABLE
                      : `${worker.profile.throughputTokensPerSecond.toLocaleString('en-US')} tokens/s`}
                  </KeyValue>
                  <KeyValue label={t('Safe chunk size')}>
                    {worker.profile.safeChunkSize === undefined
                      ? NOT_AVAILABLE
                      : `${worker.profile.safeChunkSize} candidates / round`}
                  </KeyValue>
                  <KeyValue label={t('Last heartbeat (GMT+7)')} mono>
                    {formatClock(worker.lastHeartbeatAt)}
                  </KeyValue>
                </dl>

                <p className="hint" style={{ marginBottom: 0 }}>
                  {t(
                    'GPU capacity and qualification results describe the registered device. Current usage appears in resource monitoring.',
                  )}
                </p>
              </div>
            </section>

            <section className="card" aria-label={t('Admission')}>
              <div className="ch">
                <h2>{t('Admission')}</h2>
                <small>{t('Runtime recipe admission status')}</small>
              </div>
              <div className="cb">
                <Badge info={ADMISSION_STATUS[worker.admissionStatus]} />
                <p style={{ margin: '10px 0 0' }}>{worker.admissionReason}</p>
              </div>
            </section>
          </div>

          <section className="card" aria-label={t('Worker events')}>
            <div className="ch">
              <h2>{t('Events related to this worker')}</h2>
            </div>
            {eventsFailed ? (
              <ErrorState title={t('Could not load events')} onRetry={retryRegion} retryLabel="Retry this region" />
            ) : events.length === 0 ? (
              <EmptyState title={t('No related events')} />
            ) : (
              <EventRows events={events} label={t('Worker events')} />
            )}
          </section>
        </>
      )}
    </QueryState>
  );
}
