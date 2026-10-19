import { useProduct } from '@heteroes/product-ui';
import type { WorkerStatus } from '../../types/worker';
import { Badge } from './Badge';

export function WorkerActivityBadge({ status }: { status: WorkerStatus }) {
  const { t } = useProduct();
  return status === 'ONLINE' ? (
    <Badge tone="ok" label={t('Online')} title={t('The worker is sending heartbeats to the coordinator')} />
  ) : (
    <Badge tone="neutral" label={t('Not online')} />
  );
}
