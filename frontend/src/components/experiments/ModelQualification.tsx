import { useProduct } from '@heteroes/product-ui';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { apiGet, apiPost } from '../../api/client';
import { useScopeKey, useSession } from '../../app/session';

interface ProbeDevice {
  deviceId: string;
  displayName: string;
  status: string;
  contributionEnabled: boolean;
  approvalStatus: string;
  allocatedTo?: string | null;
  selfTest: { recipeVersions?: number[]; qualifiedModelHashes?: string[] };
}
interface Job {
  jobId: string;
  deviceId: string;
  ownerUserId: string;
  status: string;
  errorCode: string | null;
}
interface Checks {
  referenceHash: string | null;
  jobs: Job[];
}
const terminal = new Set(['COMPLETED', 'CANCELLED', 'FAILED']);

export function ModelQualification({ assetId, manifestHash }: { assetId: string; manifestHash: string }) {
  const { t } = useProduct();
  const scope = useScopeKey();
  const { session, workspace } = useSession();
  const cache = useQueryClient();
  const endpoint = '/api/v1/models/' + encodeURIComponent(assetId) + '/qualifications';
  const [deviceId, setDeviceId] = useState('');
  const checks = useQuery({
    queryKey: ['model-qualifications', ...scope, assetId],
    queryFn: () => apiGet<Checks>(endpoint),
    enabled: scope.every(Boolean),
    refetchInterval: 2500,
  });
  const devices = useQuery({
    queryKey: ['model-check-devices', ...scope],
    queryFn: () => apiGet<ProbeDevice[]>('/api/v1/workers'),
    enabled: scope.every(Boolean),
    refetchInterval: 2500,
  });
  const refresh = () => cache.invalidateQueries({ predicate: (q) => q.queryKey[0] !== 'session' });
  const start = useMutation({ mutationFn: () => apiPost(endpoint, { deviceId }), onSuccess: refresh });
  const cancel = useMutation({
    mutationFn: (jobId: string) => apiPost(endpoint + '/' + jobId + '/cancel'),
    onSuccess: refresh,
  });
  const eligible =
    devices.data?.filter((d) => d.approvalStatus === 'APPROVED' && d.selfTest.recipeVersions?.includes(3)) ?? [];
  const selected = eligible.find((d) => d.deviceId === deviceId);
  const active = checks.data?.jobs.find((j) => !terminal.has(j.status));
  const ready = selected?.status === 'ONLINE' && selected.contributionEnabled && !selected.allocatedTo;
  const jobStatus = (job: Job) => {
    if (job.status === 'COMPLETED') return t('Model check passed');
    if (job.status === 'CANCELLED') return t('Model check cancelled');
    if (job.status === 'FAILED')
      return job.errorCode === 'MODEL_QUALIFICATION_MISMATCH'
        ? t('Model check did not match the lab reference.')
        : t('Model check failed. Check the Worker app and try again.');
    if (job.status === 'PREPARING') return t('Preparing model check');
    if (job.status === 'RUNNING') return t('Checking model compatibility');
    return t('Waiting for model check to stop');
  };
  return (
    <div className="demo-form">
      <h3>{t('Model compatibility')}</h3>
      <p className="hint">
        {t(
          'The first computer establishes a reference. Every other computer must reproduce it before using this model.',
        )}
      </p>
      <label className="fg">
        {t('Device for model check')}
        <select
          className="sel"
          value={deviceId}
          onChange={(e) => setDeviceId(e.target.value)}
          disabled={Boolean(active)}
        >
          <option value="">{t('Select a computer')}</option>
          {eligible.map((d) => (
            <option key={d.deviceId} value={d.deviceId}>
              {d.displayName}
            </option>
          ))}
        </select>
      </label>
      {selected && (
        <p className="hint">
          {selected.selfTest.qualifiedModelHashes?.includes(manifestHash)
            ? t('This computer is ready for this model.')
            : t('This computer needs a model check.')}
        </p>
      )}
      {!ready && !active && (
        <p className="hint">{t('Choose an online computer with contribution ON and no running job.')}</p>
      )}
      <button
        className="btn"
        disabled={!ready || Boolean(active) || start.isPending || checks.isPending || checks.isError}
        onClick={() => start.mutate()}
      >
        {t('Check compatibility')}
      </button>
      {checks.data?.jobs.slice(0, 5).map((job) => (
        <div className="demo-item" key={job.jobId}>
          <span>{eligible.find((d) => d.deviceId === job.deviceId)?.displayName ?? t('Computer')}</span>
          <span role="status">{jobStatus(job)}</span>
          {!terminal.has(job.status) && (workspace?.role === 'ADMIN' || session?.user.userId === job.ownerUserId) && (
            <button
              className="btn"
              disabled={cancel.isPending || job.status === 'CANCELLING'}
              onClick={() => cancel.mutate(job.jobId)}
            >
              {t('Cancel model check')}
            </button>
          )}
        </div>
      ))}
      {(checks.error || devices.error || start.error || cancel.error) && (
        <p role="alert">{(checks.error ?? devices.error ?? start.error ?? cancel.error)?.message}</p>
      )}
    </div>
  );
}
