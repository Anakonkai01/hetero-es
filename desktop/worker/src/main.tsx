import {
  Alert,
  CopyValue,
  PreferencesControl,
  ProductMark,
  ProductProvider,
  ResourceTelemetry,
  Status,
  StepHeader,
  useProduct,
} from '@heteroes/product-ui';
import '@heteroes/product-ui/theme.css';
import React from 'react';
import { createRoot } from 'react-dom/client';
import { ComputeSettings } from './ComputeSettings';
import { connectionMessages, explain, explanations } from './messages';
import { Station } from './Station';
import { gauges, stationView } from './station';
import './style.css';
import { useWorkerApp } from './useWorkerApp';
function App() {
  const { t } = useProduct();
  const {
    state,
    url,
    setUrl,
    username,
    setUsername,
    password,
    setPassword,
    displayName,
    setDisplayName,
    error,
    setError,
    busy,
    connectionReport,
    editLab,
    setEditLab,
    confirmForget,
    setConfirmForget,
    act,
  } = useWorkerApp();
  const step = !state?.serverUrl
    ? 0
    : !state.signedIn
      ? 1
      : !state.setup.installed || !state.selfTest?.passed
        ? 2
        : !state.device
          ? 3
          : 4;
  const approval = state?.device?.approvalStatus === 'APPROVED';
  const agent = state?.agent;
  const active = agent?.assignments.some((a) => a.workerAlive === true);
  const unknown = agent?.error || agent?.assignments.some((a) => a.workerAlive === null || a.coordinatorAlive === null);
  const contribution = unknown ? 'UNKNOWN' : agent?.enabled ? 'ON' : agent?.drained === false ? 'DRAINING' : 'OFF';
  const progress = state?.setup.progress;
  const station = state?.device
    ? stationView({
        signedIn: state.signedIn,
        device: state.device,
        connection: state.connection,
        nowSeconds: Date.now() / 1000,
        agent: state.agent,
        telemetry: state.telemetry,
      })
    : undefined;
  const stationGauges = gauges(state?.telemetry, Date.now() / 1000);
  const forgetPairing = state?.device && (
    <div className="forget-pairing">
      <p className="hint">
        {t('This computer is paired to')} <code>{state.serverUrl}</code>.{' '}
        {t('If that address no longer works, you can forget the pairing and pair again.')}
      </p>
      {!confirmForget && (
        <button type="button" className="secondary" disabled={!!busy} onClick={() => setConfirmForget(true)}>
          {t('Forget this pairing')}
        </button>
      )}
      {confirmForget && (
        <Alert tone="warning">
          {t(
            'This removes the pairing from this computer only. The lab keeps the device until an administrator removes it. You will pair again.',
          )}{' '}
          <button type="button" disabled={!!busy || !!agent?.enabled} onClick={() => void act('forgetDevice')}>
            {t('Yes, forget this pairing')}
          </button>{' '}
          <button type="button" className="secondary" onClick={() => setConfirmForget(false)}>
            {t('Cancel')}
          </button>
          {agent?.enabled && <p className="hint">{t('Stop contribution first.')}</p>}
        </Alert>
      )}
    </div>
  );
  const advanced = (
    <>
      {state && (
        <ComputeSettings
          key={`${state.compute.network}/${state.compute.coordinator}/${state.compute.host}`}
          state={state}
          busy={busy}
          act={act}
        />
      )}
      {state?.serverUrl && (
        <section className="panel">
          <div className="panel-heading">
            <h2>{t('Connection checks')}</h2>
            <button className="secondary" disabled={!!busy} onClick={() => void act('checkConnection')}>
              {t('Check connection')}
            </button>
          </div>
          <p className="hint">
            {t('This check reads network status and a small weights range. It does not start GPU work.')}
          </p>
          {connectionReport && (
            <ul className="connection-checks" aria-live="polite">
              {[...connectionReport.checks, ...connectionReport.assignments.flatMap((a) => a.checks)].map(
                (check, i) => (
                  <li key={i}>
                    <Status value={check.status} />
                    <div>
                      <b>
                        {t(
                          check.step === 'lab'
                            ? 'Lab server'
                            : check.step === 'coordinator'
                              ? 'Coordinator control'
                              : 'Full weights route',
                        )}
                      </b>
                      <p>
                        {t(connectionMessages[check.code] ?? explanations[check.code] ?? 'Lab server did not answer.')}{' '}
                        {check.status === 'FAIL' && <code>{check.code}</code>}
                      </p>
                    </div>
                  </li>
                ),
              )}
            </ul>
          )}
        </section>
      )}
    </>
  );
  return (
    <div className="desktop-shell">
      <header className="desktop-header">
        <a className="brand" href="#main">
          <ProductMark />
          <span>
            HeteroES <small>Worker</small>
          </span>
        </a>
        <PreferencesControl />
      </header>
      <main id="main">
        {!state?.device && (
          <div className="intro">
            <div>
              <p className="eyebrow">HETEROES / LAB COMPUTE</p>
              <h1>{t('Prepare this computer')}</h1>
              <p>{t('Your GPU stays OFF until you enable it.')}</p>
            </div>
            <Status value={state?.connection ?? 'CONNECTING'} />
          </div>
        )}
        {!state && <p role="status">{t('Loading…')}</p>}
        {(error === 'WINDOWS_RUNTIME_MISSING' || agent?.startError === 'WINDOWS_RUNTIME_MISSING') && (
          <button className="secondary" onClick={() => void act('external', { target: 'windowsRuntime' })}>
            {t('Install Windows runtime')}
          </button>
        )}
        {agent?.startError && !error && (
          <Alert tone="warning">
            {t('The local agent is not running. Press Enable contribution to try again.')}{' '}
            {t(explain(agent.startError))} <code>{agent.startError}</code>
          </Alert>
        )}
        {error && (
          <Alert tone="error">
            {t(explain(error))} <code>{error}</code>
          </Alert>
        )}
        {!state?.device && (
          <StepHeader
            steps={['Connect to a lab', 'Sign in', 'GPU and compatibility', 'Pair this device']}
            current={Math.min(step, 3)}
          />
        )}
        {state && !state.device && (
          <div className="onboarding">
            <section className="panel">
              <h2>
                {t(
                  step === 0
                    ? 'Connect to a lab'
                    : step === 1
                      ? 'Sign in'
                      : step === 2
                        ? 'GPU and compatibility'
                        : 'Pair this device',
                )}
              </h2>
              {(step === 0 || (step === 1 && editLab)) && (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (!url.trim()) {
                      setError('INVALID_LAB_ADDRESS');
                      return;
                    }
                    void act('connect', { url });
                  }}
                >
                  <p>
                    {t(
                      "Enter your lab address. If you downloaded this app from your lab's website, it is already filled in.",
                    )}
                  </p>
                  <label>
                    {t('Lab server address')}
                    <input
                      type="text"
                      inputMode="url"
                      autoCapitalize="off"
                      autoCorrect="off"
                      spellCheck={false}
                      placeholder={state.defaultLabUrl || 'lab.example.org'}
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                    />
                  </label>
                  <button disabled={!!busy}>{t('Connect')}</button>
                  {editLab && (
                    <button
                      type="button"
                      className="secondary"
                      disabled={!!busy}
                      onClick={() => {
                        setEditLab(false);
                        setError('');
                      }}
                    >
                      {t('Cancel')}
                    </button>
                  )}
                  <details className="advanced-panel">
                    <summary>{t('Lab on a private network (Tailscale)')}</summary>
                    <div className="secondary-actions">
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => void act('external', { target: 'tailscale' })}
                      >
                        {t('Install or sign in to Tailscale')}
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => void act('external', { target: 'help' })}
                      >
                        {t('Network help')}
                      </button>
                    </div>
                  </details>
                </form>
              )}
              {step === 1 && !editLab && (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    void act('login', { username, password });
                  }}
                >
                  <p className="hint">
                    {t('Connected to')} <code>{state.serverUrl}</code>{' '}
                    <button
                      type="button"
                      className="secondary"
                      disabled={!!busy}
                      onClick={() => {
                        setUrl(state.serverUrl);
                        setEditLab(true);
                        setError('');
                      }}
                    >
                      {t('Change lab')}
                    </button>
                  </p>
                  <p>{t('Use your own lab account.')}</p>
                  <label>
                    {t('Username')}
                    <input
                      autoComplete="username"
                      required
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                    />
                  </label>
                  <label>
                    {t('Password')}
                    <input
                      autoComplete="current-password"
                      type="password"
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                    />
                  </label>
                  <button disabled={!!busy}>{t('Sign in')}</button>
                  <button className="secondary" type="button" onClick={() => void act('connect', { url })}>
                    {t('Check connection')}
                  </button>
                </form>
              )}
              {step === 2 && (
                <>
                  <p>
                    {t(
                      'Download an isolated Python runtime, dependencies and the pinned model. No system Python is needed.',
                    )}
                  </p>
                  <p className="hint">
                    {t('Setup checks disk space and SHA-256. Interrupted downloads resume when you retry.')}
                  </p>
                  {state.setup.dataFolder && (
                    <p className="hint">
                      {t('Data folder')}: <code>{state.setup.dataFolder}</code>
                    </p>
                  )}
                  {!state.setup.installed && state.setup.profileAvailable !== false && (
                    <button
                      className="secondary"
                      type="button"
                      disabled={!!busy || state.setup.running}
                      onClick={() => void act('chooseDataFolder')}
                    >
                      {t('Use another drive or folder')}
                    </button>
                  )}
                  {state.setup.profileAvailable === false ? (
                    <Alert tone="warning">
                      {t('This development build has no runtime profile. Use the packaged installer.')}
                    </Alert>
                  ) : (
                    <button
                      disabled={!!busy || state.setup.running}
                      onClick={() => void act(state.setup.installed ? 'selftest' : 'install')}
                    >
                      {t(state.setup.installed ? 'Run compatibility check' : 'Install isolated runtime')}
                    </button>
                  )}
                  <p className="hint">
                    {t('The check repeats a GPU candidate and verifies 16 answer texts against Linux.')}
                  </p>
                </>
              )}
              {step === 3 && (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    void act('pair', { displayName });
                  }}
                >
                  <label>
                    {t('Device name')}
                    <input
                      maxLength={100}
                      required
                      value={displayName}
                      onChange={(e) => setDisplayName(e.target.value)}
                      placeholder={t('My GPU computer')}
                    />
                  </label>
                  <button disabled={!!busy}>{t('Pair device')}</button>
                  <p className="hint">
                    {t('Pairing uses a one-use code from your lab account. An administrator must approve the device.')}
                  </p>
                </form>
              )}
            </section>
            <aside className="panel guide">
              <span className="guide-icon">↗</span>
              <h2>{t('A few steps. One shared lab.')}</h2>
              <p>{t('Connect, verify your GPU, then choose when to contribute.')}</p>
              <ul>
                <li>{t('A restart always starts with contribution OFF.')}</li>
                <li>{t('Close this window to keep running in the tray.')}</li>
                <li>{t('Stop safely before shutting down this computer.')}</li>
              </ul>
            </aside>
          </div>
        )}
        {!state?.device && (
          <details className="advanced-panel">
            <summary>{t('Network, role and diagnostics')}</summary>
            {advanced}
          </details>
        )}

        {state?.device && (
          <>
            {!state.signedIn && (
              <details className="panel advanced-panel">
                <summary>{t('Sign in')}</summary>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    void act('login', { username, password });
                  }}
                >
                  <label>
                    {t('Username')}
                    <input required value={username} onChange={(e) => setUsername(e.target.value)} />
                  </label>
                  <label>
                    {t('Password')}
                    <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
                  </label>
                  <button disabled={!!busy}>{t('Sign in')}</button>
                </form>
                {forgetPairing}
              </details>
            )}
            <Station
              view={station!}
              gauges={stationGauges}
              gpuName={state.selfTest?.gpuName ?? t('Unknown')}
              vramGiB={state.selfTest ? (state.selfTest.vramTotalMb / 1024).toFixed(1) + ' GiB VRAM' : ''}
              deviceName={state.device.displayName}
              approval={state.device.approvalStatus}
              busy={!!busy}
              onToggle={() => void act('contribution', { enabled: station!.toggle.action === 'enable' })}
            >
              {advanced}
              <div className="desktop-grid">
                <div className="desktop-stack">
                  <section className="panel">
                    <div className="panel-heading">
                      <h2>{t('Device overview')}</h2>
                      <Status value={state.selfTest?.passed ? 'Ready' : 'Not yet tested'} />
                    </div>
                    <h3 className="gpu-name">{state.selfTest?.gpuName ?? t('Unknown')}</h3>
                    <dl className="desktop-details">
                      <div>
                        <dt>{t('VRAM capacity')}</dt>
                        <dd>{state.selfTest ? (state.selfTest.vramTotalMb / 1024).toFixed(1) + ' GiB' : '—'}</dd>
                      </div>
                      <div>
                        <dt>{t('Contribution')}</dt>
                        <dd>
                          <Status value={contribution} />
                        </dd>
                      </div>
                      <div>
                        <dt>{t('Approval')}</dt>
                        <dd>
                          <Status value={state.device.approvalStatus} />
                        </dd>
                      </div>
                      <div>
                        <dt>{t('Runtime')}</dt>
                        <dd>{t(state.setup.installed ? 'Installed' : 'Not installed')}</dd>
                      </div>
                    </dl>
                    <div className="preferences">
                      <label className="check">
                        <input
                          type="checkbox"
                          checked={state.startAtLogin !== false}
                          disabled={!!busy}
                          onChange={(e) => void act('preferences', { startAtLogin: e.target.checked })}
                        />
                        {t('Open with Windows')}
                      </label>
                      <label className="check">
                        <input
                          type="checkbox"
                          checked={!!state.device.keepContributionAfterReboot}
                          disabled={!!busy || !state.signedIn || state.device.approvalStatus !== 'APPROVED'}
                          onChange={(e) => void act('preferences', { keepOn: e.target.checked })}
                        />
                        {t('Keep ON after restart')}
                      </label>
                    </div>
                    <details className="desktop-detail">
                      <summary>{t('Device identity')}</summary>
                      <p>
                        <span className="hint">{t('Worker ID')}</span>
                        <code>{state.device.workerId}</code>
                      </p>
                      <p>
                        <span className="hint">{t('Physical GPU UUID')}</span>
                        <code>{state.selfTest?.gpuUUID ?? '—'}</code>
                      </p>
                    </details>
                    <button
                      className="secondary"
                      disabled={!!busy || !!agent?.enabled || agent?.drained === false}
                      onClick={() => void act('selftest')}
                    >
                      {t('Run compatibility check')}
                    </button>
                  </section>
                  <section className="panel">
                    <div className="panel-heading">
                      <h2>{t('Assignments')}</h2>
                      <span className="hint">{agent?.assignments.length ?? 0}</span>
                    </div>
                    {agent?.assignments.length ? (
                      agent.assignments.map((a) => (
                        <article className="assignment-card" key={a.assignmentId}>
                          <div className="panel-heading">
                            <span className="mono">{a.assignmentId}</span>
                            <Status
                              value={
                                a.workerAlive === true ? 'RUNNING' : a.workerAlive === false ? 'Stopped' : 'UNKNOWN'
                              }
                            />
                          </div>
                          <dl className="desktop-details">
                            <div>
                              <dt>{t('Epoch')}</dt>
                              <dd>{a.epoch ?? '—'}</dd>
                            </div>
                            <div>
                              <dt>{t('Worker process')}</dt>
                              <dd>
                                {t(
                                  a.workerAlive === true
                                    ? 'Alive'
                                    : a.workerAlive === false
                                      ? 'Confirmed stopped'
                                      : 'Unknown',
                                )}
                              </dd>
                            </div>
                            <div>
                              <dt>{t('Coordinator process')}</dt>
                              <dd>
                                {t(
                                  a.coordinatorAlive === true
                                    ? 'Alive'
                                    : a.coordinatorAlive === false
                                      ? 'Confirmed stopped'
                                      : 'Unknown',
                                )}
                              </dd>
                            </div>
                            <div>
                              <dt>{t('Compute endpoint')}</dt>
                              <dd>{t(a.ready ? 'Ready' : 'Not ready')}</dd>
                            </div>
                          </dl>
                        </article>
                      ))
                    ) : (
                      <div className="desktop-empty">
                        <span aria-hidden="true">◇</span>
                        <h3>{t('No active assignment')}</h3>
                        <p>{t('Experiments assigned to this computer will appear here.')}</p>
                      </div>
                    )}
                    <p className="hint">{t('Open the lab to inspect generations, candidates, seeds and rewards.')}</p>
                    <button
                      className="secondary"
                      disabled={!!busy}
                      onClick={() => void act('external', { target: 'lab' })}
                    >
                      {t('Open lab website')} ↗
                    </button>
                  </section>
                  <section className="panel">
                    <div className="panel-heading">
                      <h2>{t('Lab connection')}</h2>
                      <Status value={state.connection} />
                    </div>
                    <CopyValue value={state.serverUrl} label="Copy address" />
                    <dl className="desktop-details">
                      <div>
                        <dt>{t('Signed in as')}</dt>
                        <dd>{state.session?.user.displayName ?? t('Signed out')}</dd>
                      </div>
                      <div>
                        <dt>{t('Device name')}</dt>
                        <dd>{state.device.displayName}</dd>
                      </div>
                    </dl>
                    <p className="hint">
                      {t('Closing this window keeps Worker in the tray. Use Stop safely before shutting down.')}
                    </p>
                    {forgetPairing}
                  </section>
                </div>
                <aside className="panel monitoring-panel">
                  <ResourceTelemetry
                    observation={state.telemetry}
                    history={state.telemetryHistory}
                    online={state.connection === 'ONLINE'}
                  />
                </aside>
              </div>
            </Station>
          </>
        )}

        {(busy || state?.setup.running) && (
          <section className="panel" role="status">
            <h3>{t('Progress')}</h3>
            <p>{t(progress?.stage ?? busy)}</p>
            {progress?.file && <small>{progress.file}</small>}
            {progress?.total && (
              <>
                <progress max={progress.total} value={progress.received ?? 0} />
                <p>{Math.round(((progress.received ?? 0) / progress.total) * 100)}%</p>
              </>
            )}
          </section>
        )}
        <footer className="desktop-footer">
          <p className="hint">
            HeteroES Worker{state?.build ? ' · ' + state.build : ''} · {t('Contribution is your choice.')}
          </p>
          <button className="secondary" disabled={!!busy} onClick={() => void act('external', { target: 'lab' })}>
            {t('Open lab website')}
          </button>
          <button className="secondary" disabled={!!busy} onClick={() => void act('diagnostics')}>
            {t('Export diagnostics')}
          </button>
          {state?.signedIn && (
            <button className="secondary" disabled={!!busy} onClick={() => void act('logout')}>
              {t('Sign out')}
            </button>
          )}
          <button className="secondary" onClick={() => void act('quit')}>
            {t('Quit safely')}
          </button>
        </footer>
      </main>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ProductProvider>
      <App />
    </ProductProvider>
  </React.StrictMode>,
);
