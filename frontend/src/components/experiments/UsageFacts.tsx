import { useProduct } from '@heteroes/product-ui';
import { KeyValue } from '../ui/KeyValue';

export function UsageFacts({
  value,
}: {
  value?: {
    generatedTokens?: number | number[];
    auditGeneratedTokens?: number;
    gpuSeconds?: number;
    device?: 'cpu' | 'cuda';
    wallSeconds?: number;
    partial?: boolean;
  };
}) {
  const { t } = useProduct();
  if (!value) return null;
  const tokens = Array.isArray(value.generatedTokens)
    ? value.generatedTokens.reduce((sum, count) => sum + count, 0)
    : value.generatedTokens;
  const seconds =
    value.gpuSeconds ?? (value.device === 'cuda' ? value.wallSeconds : value.device === 'cpu' ? 0 : undefined);
  return (
    <>
      <KeyValue label={t('Generated tokens')} mono>
        {tokens?.toLocaleString() ?? '—'}
      </KeyValue>
      {!!value.auditGeneratedTokens && (
        <KeyValue label={t('Audit generated tokens')} mono>
          {value.auditGeneratedTokens.toLocaleString()}
        </KeyValue>
      )}
      <KeyValue label={t('Reported GPU seconds')} mono>
        {seconds?.toFixed(3) ?? '—'}
      </KeyValue>
      {value.partial && <KeyValue label={t('Usage coverage')}>{t('Partial usage reports')}</KeyValue>}
      {!Array.isArray(value.generatedTokens) && (
        <KeyValue label={t('Usage scope')}>
          {t(
            'Successful worker executions and coordinator updates; excludes idle time, validation and unreported failures.',
          )}
        </KeyValue>
      )}
    </>
  );
}
