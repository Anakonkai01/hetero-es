import { ResourceTelemetry, Status, useProduct, type ResourceObservation } from '@heteroes/product-ui';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { apiDelete, apiGet, apiPatch, apiPost } from '../api/client';
import { useSession } from '../app/session';
import { LinuxWorkerCommand } from '../components/common/LinuxWorkerCommand';
import { useInstallerManifest } from '../hooks/useInstallerManifest';
import {
  canRemoveDevice,
  defaultApprovalWorkspace,
  deviceErrorKey,
  hiddenCount,
  visibleDevices,
  workspaceName,
} from '../lib/deviceList';
export interface Device {
  deviceId: string;
  workerId: string;
  displayName: string;
  ownerUserId: string;
  approvalStatus: string;
  bootId: string | null;
  lastSeen: number;
  connectionStatus: string;
  contributionEnabled: boolean;
  keepContributionAfterReboot?: boolean;
  workspaceId: string | null;
  ownerWorkspaces?: { workspaceId: string; name: string }[];
  computeUrl: string;
  bulkUrl?: string;
  telemetry?: ResourceObservation | null;
  allocatedTo?: string;
  physicalResourceId?: string;
  selfTest: { gpuName: string; vramTotalMb: number; coordinator: boolean; passed: boolean };
}

function EndpointForm({ device, save, pending }: { device: Device; save: (body: unknown) => void; pending: boolean }) {
  const { t } = useProduct();
  const [compute, setCompute] = useState(device.computeUrl);
  const [bulk, setBulk] = useState(device.bulkUrl ?? device.computeUrl);
  return (
    <details className="advanced-panel">
      <summary>{t('Connection addresses')}</summary>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          save({ computeUrl: compute, bulkUrl: bulk });
        }}
      >
        <label className="fg">
          {t('Compute control URL')}
          <input className="inp" type="url" required value={compute} onChange={(e) => setCompute(e.target.value)} />
        </label>
        <label className="fg">
          {t('Private file transfer URL')}
          <input className="inp" type="url" required value={bulk} onChange={(e) => setBulk(e.target.value)} />
        </label>
        <p className="hint">{t('Turn contribution OFF and wait for all jobs to stop before changing addresses.')}</p>
        <button className="btn" disabled={pending || device.contributionEnabled || Boolean(device.allocatedTo)}>
          {t('Save addresses')}
        </button>
      </form>
    </details>
  );
}
/** The device's name, which its owner or an administrator can change in place. */
function DeviceTitle({ device, editable, save }: { device: Device; editable: boolean; save: (name: string) => void }) {
  const { t } = useProduct();
  const [draft, setDraft] = useState<string | null>(null);
  if (draft === null)
    return (
      <div className="device-heading">
        <h3>{device.displayName}</h3>
        {editable && (
          <button className="btn" onClick={() => setDraft(device.displayName)}>
            {t('Rename')}
          </button>
        )}
      </div>
    );
  return (
    <form
      className="device-heading"
      onSubmit={(event) => {
        event.preventDefault();
        if (draft.trim()) save(draft.trim());
        setDraft(null);
      }}
    >
      <input
        className="inp"
        aria-label={t('Device name')}
        maxLength={100}
        autoFocus
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
      />
      <button className="btn pri" disabled={!draft.trim()}>
        {t('Save')}
      </button>
      <button type="button" className="btn" onClick={() => setDraft(null)}>
        {t('Cancel')}
      </button>
    </form>
  );
}
export function LabDevices({ administration = false }: { administration?: boolean }) {
  const { t, preferences } = useProduct();
  const { session } = useSession();
  const cache = useQueryClient();
  const installer = useInstallerManifest();
  const devices = useQuery({
    queryKey: ['devices', session?.user.userId, administration],
    queryFn: () => apiGet<Device[]>(administration ? '/api/v1/platform/devices' : '/api/v1/devices'),
    enabled: Boolean(session),
    refetchInterval: 3000,
  });
  const [code, setCode] = useState('');
  const [expires, setExpires] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const [copied, setCopied] = useState(false);
  const [pairError, setPairError] = useState('');
  const [approvalTarget, setApprovalTarget] = useState<Record<string, string>>({});
  const [showRevoked, setShowRevoked] = useState(false);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const pairing = useMutation({
    mutationFn: () => apiPost<{ code: string; expiresInSeconds: number }>('/api/v1/devices/pairing-codes', {}),
    onSuccess: (r) => {
      setCode(r.code);
      setExpires(Date.now() + r.expiresInSeconds * 1000);
      setCopied(false);
      setPairError('');
    },
  });
  const action = useMutation({
    mutationFn: (a: { path: string; body?: unknown; patch?: boolean; remove?: boolean }) =>
      a.remove ? apiDelete(a.path) : a.patch ? apiPatch(a.path, a.body) : apiPost(a.path, a.body),
    onSuccess: () => cache.invalidateQueries(),
  });
  const seconds = Math.max(0, Math.ceil((expires - now) / 1000));
  return (
    <section className="card">
      <div className="ch">
        <h2>{t(administration ? 'Device approval' : 'My devices')}</h2>
      </div>
      <div className="cb">
        {(action.error || devices.error || pairing.error) && (
          <p className="note err" role="alert">
            {(() => {
              const message = (action.error ?? devices.error ?? pairing.error)?.message;
              const known = deviceErrorKey(message);
              return known ? t(known) : message;
            })()}
          </p>
        )}
        {!administration && (
          <div className="pairing-panel">
            <div>
              <b>{t('Add a GPU computer')}</b>
              {installer.data && (
                <div className="acts">
                  {installer.data.installers.map((item) => (
                    <a className="btn" key={item.platform} href={item.url} download={item.name}>
                      {t(
                        item.platform === 'windows'
                          ? 'Download Windows app'
                          : item.platform === 'linux-appimage'
                            ? 'Download AppImage'
                            : 'Download Linux app',
                      )}
                    </a>
                  ))}
                </div>
              )}
              {(installer.isError || installer.data?.installers.length === 0) && (
                <p className="hint">
                  {t(
                    'Worker downloads are unavailable on this server. Ask your administrator for the current installer.',
                  )}
                </p>
              )}
              <p>
                {t(
                  'Install HeteroES Worker, sign in, run the compatibility check and pair your device. An administrator approves it here.',
                )}
              </p>
              <p>
                {t('The desktop app creates its own one-use pairing code. This code is for an existing device agent.')}
              </p>
              <LinuxWorkerCommand manifest={installer.data} />
            </div>
            <div>
              <button className="btn" disabled={pairing.isPending} onClick={() => pairing.mutate()}>
                {t('Create pairing code')}
              </button>
              {code && (
                <>
                  <p className="pairing-code">{seconds ? code : t('Pairing code expired')}</p>
                  <p>
                    {t('Expires in')} {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')}
                  </p>
                  <button
                    className="btn"
                    disabled={!seconds}
                    onClick={() => {
                      void navigator.clipboard
                        .writeText(code)
                        .then(() => setCopied(true))
                        .catch(() => setPairError(t('Select and copy the code manually.')));
                    }}
                  >
                    {t(copied ? 'Copied' : 'Copy code')}
                  </button>
                  {pairError && <p role="alert">{pairError}</p>}
                </>
              )}
            </div>
          </div>
        )}
        {devices.isPending && <p role="status">{t('Loading…')}</p>}
        {devices.data?.length === 0 && <p className="note">{t('No devices paired yet.')}</p>}
        {administration && devices.data && hiddenCount(devices.data) > 0 && (
          <label className="fg inline">
            <input type="checkbox" checked={showRevoked} onChange={(e) => setShowRevoked(e.target.checked)} />{' '}
            {t('Show revoked devices')} ({hiddenCount(devices.data)})
          </label>
        )}
        <div className="device-cards">
          {(administration ? visibleDevices(devices.data ?? [], showRevoked) : devices.data)?.map((d) => (
            <article className="device-card" key={d.deviceId} data-device={d.workerId}>
              <DeviceTitle
                device={d}
                editable={d.ownerUserId === session?.user.userId || administration}
                save={(name) =>
                  action.mutate({ path: '/api/v1/devices/' + d.deviceId, patch: true, body: { displayName: name } })
                }
              />
              <p>
                {d.selfTest.gpuName} · {(d.selfTest.vramTotalMb / 1024).toFixed(1)} {t('GiB')}
              </p>
              <p className="device-identity">
                {d.workerId} · {t(d.selfTest.coordinator ? 'Coordinator capable' : 'Worker')}
              </p>
              <div className="device-statuses">
                <Status value={d.approvalStatus} />
                <Status value={d.connectionStatus} />
                <Status value={d.contributionEnabled ? 'ON' : 'OFF'} />
                <Status value={d.allocatedTo ? 'Allocated' : 'Idle'} />
              </div>
              <p className="hint">
                {t('Last seen:')}{' '}
                {d.lastSeen
                  ? new Date(d.lastSeen * 1000).toLocaleString(preferences.language === 'vi' ? 'vi-VN' : 'en-US')
                  : t('Never')}{' '}
                · {workspaceName(d) ?? t('Unassigned')}
              </p>
              <div className="acts">
                {administration && d.approvalStatus === 'PENDING' && (
                  <>
                    {/* the lab approves a device only into a workspace its owner belongs to */}
                    <label className="fg">
                      {t('Approval workspace')}
                      <select
                        className="sel"
                        value={approvalTarget[d.deviceId] ?? defaultApprovalWorkspace(d)}
                        onChange={(e) => setApprovalTarget({ ...approvalTarget, [d.deviceId]: e.target.value })}
                      >
                        {(d.ownerWorkspaces ?? []).map((w) => (
                          <option value={w.workspaceId} key={w.workspaceId}>
                            {w.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    {!d.ownerWorkspaces?.length && (
                      <p className="hint">{t('The owner of this device is not in any workspace yet.')}</p>
                    )}
                    <button
                      className="btn accent"
                      disabled={
                        action.isPending ||
                        !d.selfTest.passed ||
                        !(approvalTarget[d.deviceId] ?? defaultApprovalWorkspace(d))
                      }
                      onClick={() =>
                        action.mutate({
                          path: '/api/v1/platform/devices/' + d.deviceId,
                          patch: true,
                          body: {
                            approved: true,
                            workspaceId: approvalTarget[d.deviceId] ?? defaultApprovalWorkspace(d),
                          },
                        })
                      }
                    >
                      {t('Approve device')}
                    </button>
                  </>
                )}
                {administration && d.approvalStatus === 'APPROVED' && (
                  <button
                    className="btn dng"
                    disabled={action.isPending}
                    onClick={() => {
                      if (window.confirm(t('Revoke this device and request safe cancellation?')))
                        action.mutate({
                          path: '/api/v1/platform/devices/' + d.deviceId,
                          patch: true,
                          body: { approved: false },
                        });
                    }}
                  >
                    {t('Revoke device')}
                  </button>
                )}
                {(administration || d.ownerUserId === session?.user.userId) && canRemoveDevice(d) && (
                  <button
                    className="btn dng"
                    disabled={action.isPending || Boolean(d.allocatedTo)}
                    onClick={() => {
                      if (
                        window.confirm(
                          t(
                            'Delete this device? It is revoked and removed at once: the computer has to be paired again to come back. Its history stays in the audit log.',
                          ),
                        )
                      )
                        action.mutate({ path: '/api/v1/devices/' + d.deviceId, remove: true });
                    }}
                  >
                    {t(d.approvalStatus === 'PENDING' ? 'Decline and delete' : 'Delete')}
                  </button>
                )}
                {d.ownerUserId === session?.user.userId && d.approvalStatus === 'APPROVED' && (
                  <button
                    className="btn"
                    disabled={action.isPending || !d.bootId || d.connectionStatus !== 'ONLINE'}
                    onClick={() =>
                      action.mutate({
                        path: '/api/v1/devices/' + d.deviceId + '/contribution',
                        body: { enabled: !d.contributionEnabled, bootId: d.bootId },
                      })
                    }
                  >
                    {t(d.contributionEnabled ? 'Turn OFF' : 'Turn ON')}
                  </button>
                )}
                {d.ownerUserId === session?.user.userId && d.approvalStatus === 'APPROVED' && (
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={Boolean(d.keepContributionAfterReboot)}
                      disabled={action.isPending}
                      onChange={(event) =>
                        action.mutate({
                          path: '/api/v1/devices/' + d.deviceId + '/contribution',
                          patch: true,
                          body: { keepAfterReboot: event.target.checked },
                        })
                      }
                    />
                    {t('Keep ON after restart')}
                  </label>
                )}
              </div>
              {d.ownerUserId === session?.user.userId && d.selfTest.coordinator && (
                <EndpointForm
                  device={d}
                  pending={action.isPending}
                  save={(body) =>
                    action.mutate({ path: '/api/v1/devices/' + d.deviceId + '/endpoints', patch: true, body })
                  }
                />
              )}
              {!administration && (
                <details className="advanced-panel">
                  <summary>{t('Resource monitoring')}</summary>
                  <div>
                    <ResourceTelemetry observation={d.telemetry} online={d.connectionStatus === 'ONLINE'} />
                  </div>
                </details>
              )}
            </article>
          ))}
        </div>
        <p className="hint">
          {t(
            'Contribution starts OFF after each agent restart unless Keep ON after restart is ticked. A member offline for 10 minutes after its run finished no longer holds the other devices.',
          )}
        </p>
      </div>
    </section>
  );
}
