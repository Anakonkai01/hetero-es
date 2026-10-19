import { ResourceTelemetry, Status, useProduct } from '@heteroes/product-ui';
import { Link } from 'react-router';
import { QueryState } from '../../components/common/QueryState';
import { useWorkers } from '../../hooks/useWorkers';
import { formatDateTime } from '../../lib/format';
export function WorkerFleet() {
  const { t } = useProduct();
  const workers = useWorkers();
  const all = workers.data ?? [];
  const online = all.filter((worker) => worker.status === 'ONLINE'),
    offline = all.filter((worker) => worker.status !== 'ONLINE');
  const allocated = all.filter((worker) => worker.allocatedTo).length;
  return (
    <QueryState
      isPending={workers.isPending}
      isError={workers.isError}
      hasData={Boolean(workers.data)}
      title={t('Worker registry unavailable')}
    >
      {all.length > 0 && (
        <div className="fleet-summary" role="status" aria-label={t('GPU fleet summary')}>
          <div>
            <b>{online.length}</b>
            <span>{t('online')}</span>
          </div>
          <div>
            <b>{offline.length}</b>
            <span>{t('offline')}</span>
          </div>
          <div>
            <b>{allocated}</b>
            <span>{t('in use by an experiment')}</span>
          </div>
          <div>
            <b>{all.filter((worker) => worker.contributionEnabled).length}</b>
            <span>{t('contributing')}</span>
          </div>
        </div>
      )}
      <div className="resource-grid">
        {online.map((worker) => (
          <section className="card" key={worker.workerId}>
            <div className="ch resource-title">
              <div>
                <h2>{worker.displayName ?? worker.profile.gpuName}</h2>
                <span className="hint">
                  {worker.profile.gpuName} · {(worker.profile.vramTotalMb / 1024).toFixed(1)} GiB
                </span>
              </div>
              <Status value={worker.status} />
            </div>
            <div className="cb">
              <Link className="link mono" to={`/workers/${worker.workerId}`}>
                {worker.workerId}
              </Link>
              <div className="device-statuses">
                <Status value={worker.approvalStatus ?? worker.admissionStatus} />
                <Status value={worker.contributionEnabled ? 'ON' : 'OFF'} />
              </div>
              <div className="resource-assignment">
                <span>{t('Allocation')}: </span>
                {worker.allocatedTo ? (
                  <Link to={`/experiments/${worker.allocatedTo}`}>
                    {worker.activeExperimentName ?? worker.allocatedTo}
                  </Link>
                ) : (
                  t('No active allocation')
                )}
              </div>
              <ResourceTelemetry observation={worker.telemetry} history={worker.telemetryHistory} online compact />
              <details className="advanced-panel">
                <summary>{t('Device identity')}</summary>
                <div>
                  <p className="device-identity">
                    {worker.physicalResourceId ?? t('Physical GPU identity unavailable')}
                  </p>
                  <p className="info-caption">
                    {worker.admissionReason ??
                      t('Contribution, connectivity and resource ownership are independent states.')}
                  </p>
                </div>
              </details>
            </div>
          </section>
        ))}
      </div>
      {offline.length > 0 && (
        <section className="card offline-fleet">
          <div className="ch">
            <h2>{t('Offline')}</h2>
            <span className="count-badge">{offline.length}</span>
          </div>
          <ul className="offline-list">
            {offline.map((worker) => (
              <li key={worker.workerId}>
                <div>
                  <Link className="link" to={`/workers/${worker.workerId}`}>
                    <b>{worker.displayName ?? worker.workerId}</b>
                  </Link>
                  <small>
                    {worker.profile.gpuName} · {(worker.profile.vramTotalMb / 1024).toFixed(1)} GiB
                  </small>
                </div>
                <div className="device-statuses">
                  <Status value={worker.status} />
                  <Status value={worker.approvalStatus ?? worker.admissionStatus} />
                  <Status value={worker.contributionEnabled ? 'ON' : 'OFF'} />
                </div>
                <small className="hint">
                  {worker.lastHeartbeatAt
                    ? `${t('Last seen:')} ${formatDateTime(worker.lastHeartbeatAt)}`
                    : t('Never connected')}
                </small>
              </li>
            ))}
          </ul>
        </section>
      )}
      {all.length === 0 && (
        <div className="empty">
          <b>{t('No workers registered')}</b>
          <span>{t('Pair a GPU computer to start monitoring it here.')}</span>
        </div>
      )}
    </QueryState>
  );
}
