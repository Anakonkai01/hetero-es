import { RuntimeConfiguration } from './RuntimeConfiguration';
import { useProduct } from '@heteroes/product-ui';
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { apiPatch, apiPost } from '../../api/client';
import { archiveExperiment, requestExperimentCancel, submitExperiment, updateExperiment } from '../../api/experiments';
import { useSession } from '../../app/session';
import { useAccessMutation } from '../../hooks/useAccess';
import type { Experiment } from '../../types/experiment';
export function RuntimeControls({ experiment: e }: { experiment: Experiment }) {
  const { t } = useProduct();
  const { session, workspace } = useSession();
  const navigate = useNavigate();
  const submit = useAccessMutation(submitExperiment);
  const cancel = useAccessMutation(requestExperimentCancel);
  const pause = useAccessMutation((id: string) => apiPost(`/api/v1/experiments/${id}/pause`));
  const resume = useAccessMutation((id: string) => apiPost(`/api/v1/experiments/${id}/resume`));
  const archive = useAccessMutation(archiveExperiment);
  const edit = useAccessMutation(updateExperiment);
  const [editing, setEditing] = useState(false);
  const policy = useAccessMutation((value: { interval: number; retain: number }) =>
    apiPatch(`/api/v1/experiments/${e.experimentId}/backup-policy`, value),
  );
  const [backupInterval, setBackupInterval] = useState(
    e.requestedBackupPolicy?.interval ?? e.backupPolicy?.interval ?? 1,
  );
  const [backupRetain, setBackupRetain] = useState(e.requestedBackupPolicy?.retain ?? e.backupPolicy?.retain ?? 3);
  const permitted = e.ownerUserId === session?.user.userId || workspace?.role === 'ADMIN';
  const terminal = ['COMPLETED', 'CANCELLED', 'FAILED', 'DRAFT'].includes(e.status);
  const error = submit.error ?? cancel.error ?? archive.error ?? edit.error ?? pause.error ?? resume.error;
  const busy =
    submit.isPending || cancel.isPending || archive.isPending || edit.isPending || pause.isPending || resume.isPending;
  return (
    <section className="card experiment-management" aria-label={t('Experiment management')}>
      <div className="cb demo-form">
        <div className="mgmt-row">
          <div className="gpu-chips">
            <span className="hint">{t('GPUs')}</span>
            {e.workerIds?.map((id) => (
              <span className="chip" key={id}>
                {id}
              </span>
            ))}
          </div>
          {e.waitingReason && <p className="note">{t(e.waitingReason)}</p>}

          {e.monitoringPartial && (
            <p>{t('Dashboard details show recent history. Full canonical history is retained in recovery points.')}</p>
          )}
          {e.failureReason && (
            <p className="note err" role="alert">
              {t(e.failureReason)}
            </p>
          )}
          {error && (
            <p className="note err" role="alert">
              {t(error.message)}
            </p>
          )}
          {permitted && (
            <div className="acts mgmt-actions">
              {e.status === 'DRAFT' && (
                <>
                  <button className="btn" disabled={busy} onClick={() => setEditing(!editing)}>
                    {t('Edit configuration')}
                  </button>
                  <button
                    className="btn pri"
                    disabled={busy}
                    onClick={() => void submit.mutateAsync(e.experimentId).catch(() => {})}
                  >
                    {t('Start experiment')}
                  </button>
                </>
              )}
              {!terminal && !e.cancelRequested && (
                <button
                  className="btn dng"
                  disabled={busy}
                  onClick={() => void cancel.mutateAsync(e.experimentId).catch(() => {})}
                >
                  {t('Cancel experiment')}
                </button>
              )}
              {e.coordinatorDeviceId && ['STARTING', 'RUNNING'].includes(e.status) && !e.cancelRequested && (
                <button
                  className="btn"
                  disabled={busy}
                  onClick={() => void pause.mutateAsync(e.experimentId).catch(() => {})}
                >
                  {t('Pause after generation')}
                </button>
              )}
              {e.coordinatorDeviceId && e.status === 'PAUSED' && !e.cancelRequested && (
                <button
                  className="btn pri"
                  disabled={busy}
                  onClick={() => void resume.mutateAsync(e.experimentId).catch(() => {})}
                >
                  {t('Resume experiment')}
                </button>
              )}

              {terminal && (
                <button
                  className="btn dng"
                  disabled={busy}
                  onClick={() => {
                    if (window.confirm('Archive this experiment and retain its evidence?'))
                      void archive
                        .mutateAsync(e.experimentId)
                        .then(() => navigate('/experiments'))
                        .catch(() => {});
                  }}
                >
                  {t('Archive')}
                </button>
              )}
            </div>
          )}
        </div>
        {e.cancelRequested && !terminal && (
          <p className="note">
            {t(
              'Stopping new leases; waiting for current candidates to restore and all selected workers to stop. The last completed checkpoint is retained.',
            )}
          </p>
        )}
        {e.status === 'PAUSING' && !e.cancelRequested && (
          <p className="note">
            {t(
              'Finishing this generation, verifying its checkpoint and waiting for all selected processes to stop before releasing GPUs.',
            )}
          </p>
        )}
        {e.status === 'PAUSED' && (
          <p className="note">
            {t(
              'Checkpoint verified and GPUs released. Resume queues the same experiment with its frozen configuration and new assignment credentials.',
            )}
          </p>
        )}
        {permitted && e.coordinatorDeviceId && !['COMPLETED', 'CANCELLED', 'FAILED'].includes(e.status) && (
          <details className="advanced-panel">
            <summary>{t('Backup policy')}</summary>
            <div>
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  policy.mutate({ interval: backupInterval, retain: backupRetain });
                }}
              >
                <label className="fg">
                  {t('Backup interval')}
                  <input
                    className="inp"
                    type="number"
                    required
                    min={1}
                    max={1000}
                    value={backupInterval}
                    onChange={(event) => setBackupInterval(Number(event.target.value))}
                  />
                </label>
                <label className="fg">
                  {t('Recovery points to retain')}
                  <input
                    className="inp"
                    type="number"
                    required
                    min={1}
                    max={1000}
                    value={backupRetain}
                    onChange={(event) => setBackupRetain(Number(event.target.value))}
                  />
                </label>
                <button className="btn" disabled={policy.isPending}>
                  {t('Apply backup policy at next generation')}
                </button>
                {policy.error && <p role="alert">{policy.error.message}</p>}
              </form>
            </div>
          </details>
        )}
        {editing && e.status === 'DRAFT' && (
          <RuntimeConfiguration
            initial={e}
            pending={edit.isPending}
            onSave={async (configuration) => {
              await edit.mutateAsync({ experimentId: e.experimentId, configuration });
              setEditing(false);
            }}
          />
        )}
      </div>
    </section>
  );
}
