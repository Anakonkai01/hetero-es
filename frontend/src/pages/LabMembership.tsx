import { useProduct } from '@heteroes/product-ui';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { apiDelete, apiGet, apiPatch, apiPost } from '../api/client';
import { useSession } from '../app/session';
import { useResources } from '../hooks/useAccess';

export function LabMembership() {
  const { t } = useProduct();
  const { workspace, refreshSession } = useSession();
  const query = useResources();
  const cache = useQueryClient();
  const [username, setUsername] = useState('');
  const mutation = useMutation({
    mutationFn: (input: { path: string; method: 'POST' | 'PATCH' | 'DELETE'; body?: unknown }) =>
      input.method === 'DELETE'
        ? apiDelete(input.path)
        : input.method === 'PATCH'
          ? apiPatch(input.path, input.body)
          : apiPost(input.path, input.body),
    onSuccess: async () => {
      await cache.invalidateQueries();
      await refreshSession();
      setUsername('');
    },
  });
  const admin = workspace?.role === 'ADMIN';
  const prefix = `/api/v1/workspaces/${workspace?.workspaceId}`;
  const listed = useQuery({
    queryKey: ['listed-workspaces'],
    queryFn: () => apiGet<{ workspaceId: string }[]>('/api/v1/listed-workspaces'),
  });
  const requests = useQuery({
    queryKey: ['join-requests', workspace?.workspaceId],
    queryFn: () => apiGet<{ requestId: string; username: string; displayName?: string }[]>(prefix + '/join-requests'),
    enabled: admin,
    refetchInterval: 10000,
  });
  const isListed = Boolean(listed.data?.some((w) => w.workspaceId === workspace?.workspaceId));
  const capabilities = useQuery({
    queryKey: ['capabilities', workspace?.workspaceId],
    queryFn: () =>
      apiGet<{
        coordinatorDevices?: { deviceId: string; workerId: string; displayName?: string }[];
        defaultCoordinatorDeviceId?: string | null;
      }>('/api/v1/capabilities'),
    enabled: admin,
  });
  return (
    <section className="card">
      <div className="ch">
        <h2>{t('Members')}</h2>
      </div>
      <div className="cb demo-form">
        <p>
          {admin
            ? t('Workspace administrators can view and cancel all workspace experiments.')
            : t('You can view your own experiments.')}
        </p>
        {admin && (
          <form
            className="demo-form"
            onSubmit={(e) => {
              e.preventDefault();
              mutation.mutate({ path: prefix + '/invitations', method: 'POST', body: { username } });
            }}
          >
            <label className="fg">
              {t('Invite by username')}
              <input
                className="inp"
                required
                minLength={3}
                maxLength={64}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </label>
            <button className="btn accent" disabled={mutation.isPending}>
              {t('Invite member')}
            </button>
          </form>
        )}
        {admin && (
          <label className="fg inline">
            <input
              type="checkbox"
              checked={isListed}
              disabled={mutation.isPending || listed.isPending}
              onChange={(e) =>
                mutation.mutate({ path: prefix + '/listing', method: 'PATCH', body: { listed: e.target.checked } })
              }
            />{' '}
            {t('List this workspace so researchers can ask to join')}
          </label>
        )}
        {admin && (
          <label className="fg">
            {t('Default coordinator of this workspace')}
            <select
              className="sel"
              value={capabilities.data?.defaultCoordinatorDeviceId ?? ''}
              disabled={mutation.isPending || !capabilities.data}
              onChange={(e) =>
                mutation.mutate({
                  path: prefix + '/default-coordinator',
                  method: 'PATCH',
                  body: { deviceId: e.target.value || null },
                })
              }
            >
              <option value="">{t('None (choose for each experiment)')}</option>
              {capabilities.data?.coordinatorDevices?.map((d) => (
                <option key={d.deviceId} value={d.deviceId}>
                  {d.displayName ?? d.workerId}
                </option>
              ))}
            </select>
          </label>
        )}
        {admin &&
          requests.data?.map((r) => (
            <div className="request-card" key={r.requestId}>
              <span>
                {t('Asks to join:')} {r.displayName ?? r.username} · {r.username}
              </span>
              <div className="acts">
                <button
                  className="btn accent"
                  disabled={mutation.isPending}
                  onClick={() =>
                    mutation.mutate({
                      path: `${prefix}/join-requests/${r.requestId}`,
                      method: 'POST',
                      body: { approve: true },
                    })
                  }
                >
                  {t('Approve')}
                </button>
                <button
                  className="btn"
                  disabled={mutation.isPending}
                  onClick={() =>
                    mutation.mutate({
                      path: `${prefix}/join-requests/${r.requestId}`,
                      method: 'POST',
                      body: { approve: false },
                    })
                  }
                >
                  {t('Reject')}
                </button>
              </div>
            </div>
          ))}
        {mutation.error && (
          <p className="note err" role="alert">
            {mutation.error.message}
          </p>
        )}
        {mutation.isSuccess && <p role="status">{t('Membership operation saved.')}</p>}
        {query.data?.members.map((m) => (
          <div className="request-card" key={m.user.userId}>
            <span>
              {m.user.displayName} · {m.user.username} · {t(m.role === 'ADMIN' ? 'Administrator' : 'Participant')}
            </span>
            {admin && (
              <div className="acts">
                <button
                  className="btn"
                  disabled={mutation.isPending}
                  onClick={() =>
                    mutation.mutate({
                      path: prefix + '/members/' + m.user.userId,
                      method: 'PATCH',
                      body: { role: m.role === 'ADMIN' ? 'PARTICIPANT' : 'ADMIN' },
                    })
                  }
                >
                  {t(m.role === 'ADMIN' ? 'Make participant' : 'Make administrator')}
                </button>
                <button
                  className="btn dng"
                  disabled={mutation.isPending}
                  onClick={() => {
                    if (
                      window.confirm(
                        `${m.user.username}: ${t('Remove this member? Their queued jobs will be cancelled and active jobs will drain.')}`,
                      )
                    )
                      mutation.mutate({ path: prefix + '/members/' + m.user.userId, method: 'DELETE' });
                  }}
                >
                  {t('Remove member')}
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
