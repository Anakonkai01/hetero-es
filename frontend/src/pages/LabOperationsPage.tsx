import { useProduct } from '@heteroes/product-ui';
import { PageHeader } from '../components/ui/PageHeader';
import { LabDevices } from './LabDevices';
import {
  LabAccountApprovals,
  LabPlatformActivity,
  LabRecoveryPanel,
  LabServiceReservations,
} from './LabOperationsSections';
import { useLabOperations } from './useLabOperations';
export function LabOperationsPage() {
  const { t } = useProduct();
  const state = useLabOperations();
  const { allowed, action } = state;
  if (!allowed) return <p role="alert">{t('Platform administrator permission required.')}</p>;
  return (
    <>
      <PageHeader title={t('Lab operations')} description={t('Accounts, service health and safe maintenance.')} />
      {action.error && (
        <p className="note err" role="alert">
          {action.error.message}
        </p>
      )}
      <LabAccountApprovals state={state} />
      <LabDevices administration />
      <LabServiceReservations state={state} />
      <LabRecoveryPanel state={state} />
      <LabPlatformActivity state={state} />
    </>
  );
}
