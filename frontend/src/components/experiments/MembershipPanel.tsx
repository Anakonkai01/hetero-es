import { useProduct } from '@heteroes/product-ui';
import { useState } from 'react';
import { apiPost } from '../../api/client';
import { useAccessMutation } from '../../hooks/useAccess';
import { useWorkers } from '../../hooks/useWorkers';
import { memberView } from '../../lib/membership';
import type { Experiment } from '../../types/experiment';

const STATE_LABEL = { member: '', joining: 'joining', leaving: 'leaving', left: 'left' } as const;

// Workers of the experiment; while it runs its owner can add or remove one (ADR-009), from the next generation on.
export function MembershipPanel({ experiment: e, permitted }: { experiment: Experiment; permitted: boolean }) {
  const { t } = useProduct();
  const workers = useWorkers();
  const [choice, setChoice] = useState('');
  const change = useAccessMutation((body: { workerId: string; action: 'add' | 'remove' }) =>
    apiPost(`/api/v1/experiments/${e.experimentId}/workers`, body),
  );
  const view = memberView(e);
  const active = view.filter((m) => m.state === 'member' || m.state === 'joining');
  const running = ['STARTING', 'RUNNING'].includes(e.status) && !e.cancelRequested;
  const candidates = (workers.data ?? []).filter(
    (w) => !view.some((m) => m.workerId === w.workerId && m.state !== 'left'),
  );
  return (
    <div className="gpu-chips">
      <span className="hint">{t('GPUs')}</span>
      {view.map(({ workerId, state }) => (
        <span className={`chip${state === 'left' ? ' muted' : ''}`} key={workerId}>
          {workerId}
          {STATE_LABEL[state] && <small> · {t(STATE_LABEL[state])}</small>}
          {permitted && running && state === 'member' && active.length > 1 && (
            <button
              type="button"
              className="chip-x"
              aria-label={t('Remove worker')}
              disabled={change.isPending}
              onClick={() => void change.mutateAsync({ workerId, action: 'remove' }).catch(() => {})}
            >
              ×
            </button>
          )}
        </span>
      ))}
      {e.allowJoin && <span className="hint">{t('Idle eligible workers join by themselves')}</span>}
      {permitted && running && candidates.length > 0 && (
        <span className="acts">
          <select className="sel" value={choice} onChange={(event) => setChoice(event.target.value)}>
            <option value="">{t('Add a worker')}</option>
            {candidates.map((w) => (
              <option key={w.workerId} value={w.workerId}>
                {w.displayName ?? w.workerId} · {w.profile.gpuName}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="btn"
            disabled={!choice || change.isPending}
            onClick={() =>
              void change
                .mutateAsync({ workerId: choice, action: 'add' })
                .then(() => setChoice(''))
                .catch(() => {})
            }
          >
            {t('Add')}
          </button>
        </span>
      )}
      {running && view.some((m) => m.state === 'joining' || m.state === 'leaving') && (
        <span className="hint">{t('Changes apply at the next generation.')}</span>
      )}
      {change.error && (
        <p className="note err" role="alert">
          {t(change.error.message)}
        </p>
      )}
    </div>
  );
}
