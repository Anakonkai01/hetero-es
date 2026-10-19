import { useProduct } from '@heteroes/product-ui';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { apiGet } from '../api/client';
import { useScopeKey } from '../app/session';
import { EmptyState } from '../components/common/EmptyState';
import { useExperiments } from '../hooks/useExperiments';
export function LabQueue({ showEmpty = false }: { showEmpty?: boolean }) {
  const { t } = useProduct();
  const scope = useScopeKey();
  const runs = useExperiments();
  const queue = useQuery({
    queryKey: ['queue', ...scope],
    queryFn: () => apiGet<{ experimentId: string; position: number; reason: string }[]>('/api/v1/queue'),
    enabled: scope.every(Boolean),
    refetchInterval: 2500,
  });
  if (!showEmpty && queue.data?.length === 0) return null;
  return (
    <section className="card">
      <div className="ch">
        <h2>{t('Queue')}</h2>
        <span className="hint">
          {queue.data?.length ?? '—'} {t('waiting')}
        </span>
      </div>
      {queue.isError ? (
        <p className="cb note err" role="alert">
          {t('Queue status unavailable.')}
        </p>
      ) : queue.isPending ? (
        <p className="cb" role="status">
          {t('Loading…')}
        </p>
      ) : queue.data?.length ? (
        <div className="cb">
          {queue.data.map((row) => (
            <div className="queue-entry" key={row.experimentId}>
              <span>{row.position}</span>
              <div>
                <Link to={`/experiments/${row.experimentId}`}>
                  {runs.data?.find((e) => e.experimentId === row.experimentId)?.name ?? row.experimentId}
                </Link>
                <p>{t(row.reason || 'Waiting for resources')}</p>
              </div>
              <Link className="link" to={`/experiments/${row.experimentId}`} aria-label={t('Open experiment')}>
                →
              </Link>
            </div>
          ))}
        </div>
      ) : (
        <EmptyState
          title={t('Queue is clear')}
          message="Submitted experiments appear here while they wait for resources."
        />
      )}
    </section>
  );
}
