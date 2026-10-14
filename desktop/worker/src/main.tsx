import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ProductProvider, PreferencesControl, StepHeader, Status, Alert, ProductMark, CopyValue, ResourceTelemetry, type ResourceObservation,type ResourceHistoryPoint, useProduct } from '@heteroes/product-ui';
import '@heteroes/product-ui/theme.css';
import './style.css';
import { Station } from './Station';
import { gauges, stationView } from './station';
type SetupState = {
    installed: boolean;
    running: boolean;
    profileAvailable?: boolean;
    progress: {
        stage: string;
        file?: string;
        received?: number;
        total?: number;
        iteration?: number;
        code?: string;
    };
};
type State = {
    compute: { pending?: boolean; network: string; coordinator: boolean; host: string; eligible: boolean;
        addresses: { host: string; name: string; network: string }[] };
    telemetry?:ResourceObservation|null;
    telemetryHistory?:ResourceHistoryPoint[];
    serverUrl: string;
    defaultLabUrl?: string;
    build?: string;
    signedIn: boolean;
    session?: {
        user: {
            displayName: string;
        };
    };
    connection: string;
    device?: {
        deviceId: string;
        workerId: string;
        displayName: string;
        approvalStatus: string;
    };
    selfTest?: {
        passed: boolean;
        gpuName: string;
        vramTotalMb: number;
        gpuUUID?: string;
    };
    setup: SetupState;
    agent?: {
        enabled: boolean;
        drained: boolean;
        error?: string;
        startError?: string;
        assignments: {
            assignmentId: string;
            epoch?:number;
            ready?:boolean;
            workerAlive: boolean | null;
            coordinatorAlive: boolean | null;
        }[];
    };
};
type ConnectionCheck = { step: string; status: string; code: string };
type ConnectionReport = { checks: ConnectionCheck[]; assignments: { assignmentId: string; replayOnly?: boolean; checks: ConnectionCheck[] }[] };
const connectionMessages: Record<string, string> = {
    LAB_REACHABLE: 'Lab server is reachable.', CONTROL_REACHABLE: 'Coordinator accepted the compute credential.',
    BULK_REACHABLE: 'A 64-byte weights range was received.', NO_ASSIGNMENT: 'Not tested yet: no current worker assignment.',
    REPLAY_ONLY: 'Public route: replay only. Full weights need the private network.',
    NO_PUBLISHED_WEIGHTS: 'Not tested yet: no weights are published for this job.',
    COORDINATOR_UNREACHABLE: 'Coordinator did not answer on the private or public route.',
    CONTROL_REQUIRED: 'Check coordinator control before checking weights.', BULK_CHECK_FAILED: 'Could not read a bounded weights range on the private route.',
    LAB_UNREACHABLE: 'Lab server did not answer.', AGENT_CHECK_FAILED: 'Could not obtain connection checks from the local agent.', PROBE_LIMIT: 'Not tested yet: another retained assignment was checked first.',
};

function ComputeSettings({ state, busy, act }: { state: State; busy: string; act: (action: string, args?: Record<string, unknown>) => Promise<void> }) {
    const { t } = useProduct();
    const [network, setNetwork] = useState(state.compute.network);
    const [coordinator, setCoordinator] = useState(state.compute.coordinator);
    const choices = state.compute.addresses.filter(a => network === 'internet' || a.network === network);
    const [host, setHost] = useState(state.compute.host);
    const selectedHost = choices.some(a => a.host === host) ? host : (choices[0]?.host ?? '');
    const locked = !!busy || state.setup.running || (!state.compute.pending && (!!state.agent?.enabled || state.agent?.drained === false)) || (!!state.device && !state.signedIn);
    return <section className="panel"><h2>{t('Network and compute role')}</h2>
        {state.compute.pending && <Alert tone="warning">{t('The last server reply was lost. Sign in and save the chosen role again to confirm it. The agent stays stopped.')}</Alert>}
        <form onSubmit={e => { e.preventDefault(); void act('configureCompute', { network, coordinator, host: selectedHost }); }}>
            <label>{t('Network')}<select aria-label={t('Network')} disabled={locked} value={network} onChange={e => setNetwork(e.target.value)}>
                <option value="lan">{t('Same LAN')}</option><option value="overlay">{t('Tailscale / WireGuard')}</option><option value="internet">{t('Internet over HTTPS')}</option>
            </select></label>
            <p className="hint">{t(network === 'internet' ? 'Public route: replay only. Full weights need the private network.' : 'Keep the selected private address fixed. Remote workers must be able to reach it.')}</p>
            {state.compute.eligible && <label className="role-toggle"><input type="checkbox" checked={coordinator} disabled={locked} onChange={e => setCoordinator(e.target.checked)}/>{t('Allow this computer to coordinate experiments')}</label>}
            {!state.compute.eligible && <p className="hint">{t('Coordinator requires a qualified Linux GPU with at least 11000 MB VRAM.')}</p>}
            {coordinator && <label>{t('Coordinator private address')}<select aria-label={t('Coordinator private address')} value={selectedHost} disabled={locked} required onChange={e => setHost(e.target.value)}>
                {!choices.length && <option value="">{t('No private address found')}</option>}{choices.map(a => <option key={a.host} value={a.host}>{a.host} · {a.name}</option>)}
            </select></label>}
            <button disabled={locked || (coordinator && (!state.compute.eligible || !selectedHost))}>{t('Save network and role')}</button>
            <p className="hint">{t('Stop contribution and wait for all processes to drain before changing the role.')}</p>
        </form>
    </section>;
}
declare global {
    interface Window {
        worker: {
            call: (action: string, args?: Record<string, unknown>) => Promise<{
                ok: boolean;
                result?: unknown;
                error?: string;
            }>;
        };
    }
}
const explanations: Record<string, string> = { LAB_HTTP_401: 'Incorrect username or password. Sign in again.', LAB_HTTP_403: 'This action requires the device owner or administrator.', LAB_HTTP_409: 'The device or assignment is not ready. Refresh and try again.', SELF_TEST_REQUIRED: 'Run the GPU compatibility check before pairing.', SECURE_STORAGE_REQUIRED: 'Secure credential storage is unavailable. Unlock your system keyring and restart.', INSUFFICIENT_DISK_SPACE: 'Free some disk space and retry. Partial downloads are kept.', CUDA_UNAVAILABLE: 'CUDA_UNAVAILABLE', WINDOWS_RUNTIME_MISSING: 'WINDOWS_RUNTIME_MISSING', COMPATIBILITY_FAILED: 'The numerical check failed. Keep contribution OFF and export diagnostics.', AGENT_UNAVAILABLE: 'A process state is unknown; resources remain reserved.', RUNTIME_PROCESS_FAILED: 'Runtime setup or GPU check failed. Export diagnostics and retry.', ACTION_IN_PROGRESS: 'Wait for the current action to finish.', DRAIN_NOT_CONFIRMED: 'Waiting for owned processes to stop.', SETUP_IN_PROGRESS: 'Wait for runtime setup or the compatibility check to finish.' };
Object.assign(explanations, { LAB_UPDATE_REQUIRED: 'This lab needs a server update before changing a paired device role.', STOP_WORK_FIRST: 'Stop contribution and wait for all processes to drain.', INVALID_COMPUTE_ADDRESS: 'Select an available private address on this computer.', COORDINATOR_NOT_QUALIFIED: 'Coordinator requires a qualified Linux GPU with at least 11000 MB VRAM.' });
Object.assign(explanations, {
    INVALID_LAB_ADDRESS: 'This is not a valid lab address. Example: lab.example.org', HTTPS_OR_PRIVATE_NETWORK_REQUIRED: 'Use an https:// address. Plain http:// is only allowed for private network addresses.',
    LAB_UNREACHABLE: 'The lab did not answer. Check the address and your internet connection.', LAB_TIMEOUT: 'The lab took too long to answer. Check the address and try again.',
    NOT_A_LAB: 'This address answered, but it is not a HeteroES lab.', LAB_AGENT_MODE_REQUIRED: 'This lab does not accept desktop Workers yet. Ask its administrator to update it.',
    LAB_BAD_RESPONSE: 'The lab sent a reply this app does not understand. Update the app or ask the administrator.', DIFFERENT_LAB_REQUIRES_NEW_PAIRING: 'This computer is paired to another lab. Pair it again to use this one.',
    LAB_DNS_FAILED: 'This computer could not find the lab address. Check the spelling, your DNS or VPN settings.',
    LAB_CONNECTION_REFUSED: 'The lab refused the connection. It may be restarting, or a firewall is blocking it.',
    LAB_CONNECTION_RESET: 'The connection to the lab was cut. A firewall, antivirus or proxy may be inspecting it.',
    LAB_NETWORK_DOWN: 'There is no network route to the lab. Check your internet or VPN connection.',
    LAB_CERTIFICATE_REJECTED: 'This computer does not trust the lab\'s security certificate. Antivirus or a proxy that inspects HTTPS is the usual cause.',
    OLD_LAB_UNREACHABLE: 'The lab this computer was paired to cannot be reached (an address that needs Tailscale does not work while Tailscale is off). Turn Tailscale on, or press Forget this pairing and pair again.',
    AGENT_SPAWN_FAILED: 'The local agent program could not be started. The runtime may be incomplete or blocked by antivirus software. Export diagnostics.',
    AGENT_EXITED: 'The local agent stopped right after it started. Export diagnostics and send the log file.',
    SELECT_LAB_FIRST: 'Enter the lab address first.', SIGN_IN_REQUIRED: 'Sign in first.', ACTION_CANCELLED: 'Cancelled.',
});
const explain = (code: string) => explanations[code] ?? (/^LAB_HTTP_5\d\d$/.test(code) ? 'The lab server is not answering right now. Try again later or ask the lab administrator.' : 'Could not complete the action. Check the connection and export diagnostics.');

function App() {
    const { t } = useProduct();
    const [state, setState] = useState<State>();
    const [url, setUrl] = useState('');
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [displayName, setDisplayName] = useState('');
    const [error, setError] = useState('');
    const [busy, setBusy] = useState('');
    const [connectionReport, setConnectionReport] = useState<ConnectionReport>();
    const [editLab, setEditLab] = useState(false);
    const [confirmForget, setConfirmForget] = useState(false);
    const polling = useRef(false);
    const quitting = useRef(false);
    async function refresh() { if (polling.current || quitting.current)
        return; polling.current = true; try {
        const row = await window.worker.call('status');
        if (row.ok) {
            const s = row.result as State;
            setState(s);
            setUrl(old => old || s.serverUrl || s.defaultLabUrl || '');
        }
        else
            setError(row.error ?? 'ACTION_FAILED');
    }
    catch {
        setError('AGENT_UNAVAILABLE');
    }
    finally {
        polling.current = false;
    } }
    useEffect(() => { void refresh(); const timer = setInterval(() => void refresh(), 3000); return () => clearInterval(timer); }, []);
    async function act(action: string, args: Record<string, unknown> = {}) { setBusy(action); setError(''); try {
        const row = await window.worker.call(action, args);
        if (!row.ok) {
            setError(row.error ?? 'ACTION_FAILED');
            return;
        }
        if (action === 'login')
            setPassword('');
        if (action === 'checkConnection') setConnectionReport(row.result as ConnectionReport);
        if (action === 'configureCompute' || action === 'connect') setConnectionReport(undefined);
        if (action === 'forgetDevice') { setConnectionReport(undefined); setConfirmForget(false); setUrl(state?.defaultLabUrl ?? ''); }
        if (action === 'connect') setEditLab(false);
        if (action === 'quit') {
            if ((row.result as {
                drained: boolean;
            }).drained)
                quitting.current = true;
            else
                setError('DRAIN_NOT_CONFIRMED');
        }
        await refresh();
    }
    catch {
        setError('ACTION_FAILED');
    }
    finally {
        setBusy('');
    } }
    const step = !state?.serverUrl ? 0 : !state.signedIn ? 1 : !state.setup.installed || !state.selfTest?.passed ? 2 : !state.device ? 3 : 4;
    const approval = state?.device?.approvalStatus === 'APPROVED';
    const agent = state?.agent;
    const active = agent?.assignments.some(a => a.workerAlive === true);
    const unknown = agent?.error || agent?.assignments.some(a => a.workerAlive === null || a.coordinatorAlive === null);
    const contribution = unknown ? 'UNKNOWN' : agent?.enabled ? 'ON' : agent?.drained === false ? 'DRAINING' : 'OFF';
    const progress = state?.setup.progress;
    const station = state?.device ? stationView({ signedIn: state.signedIn, device: state.device, connection: state.connection, nowSeconds: Date.now() / 1000, agent: state.agent, telemetry: state.telemetry }) : undefined;
    const stationGauges = gauges(state?.telemetry, Date.now() / 1000);
    const forgetPairing = state?.device && <div className="forget-pairing">
        <p className="hint">{t('This computer is paired to')} <code>{state.serverUrl}</code>. {t('If that address no longer works, you can forget the pairing and pair again.')}</p>
        {!confirmForget && <button type="button" className="secondary" disabled={!!busy} onClick={() => setConfirmForget(true)}>{t('Forget this pairing')}</button>}
        {confirmForget && <Alert tone="warning">{t('This removes the pairing from this computer only. The lab keeps the device until an administrator removes it. You will pair again.')} <button type="button" disabled={!!busy || !!agent?.enabled} onClick={() => void act('forgetDevice')}>{t('Yes, forget this pairing')}</button> <button type="button" className="secondary" onClick={() => setConfirmForget(false)}>{t('Cancel')}</button>{agent?.enabled && <p className="hint">{t('Stop contribution first.')}</p>}</Alert>}
    </div>;
    const advanced = <>
  {state && <ComputeSettings key={`${state.compute.network}/${state.compute.coordinator}/${state.compute.host}`} state={state} busy={busy} act={act}/>}
 {state?.serverUrl && <section className="panel"><div className="panel-heading"><h2>{t('Connection checks')}</h2><button className="secondary" disabled={!!busy} onClick={() => void act('checkConnection')}>{t('Check connection')}</button></div>
 <p className="hint">{t('This check reads network status and a small weights range. It does not start GPU work.')}</p>
 {connectionReport && <ul className="connection-checks" aria-live="polite">{[...connectionReport.checks, ...connectionReport.assignments.flatMap(a => a.checks)].map((check, i) => <li key={i}><Status value={check.status}/><div><b>{t(check.step === 'lab' ? 'Lab server' : check.step === 'coordinator' ? 'Coordinator control' : 'Full weights route')}</b><p>{t(connectionMessages[check.code] ?? explanations[check.code] ?? 'Lab server did not answer.')} {check.status === 'FAIL' && <code>{check.code}</code>}</p></div></li>)}</ul>}
 </section>}
    </>;
    return <div className="desktop-shell"><header className="desktop-header"><a className="brand" href="#main"><ProductMark/><span>HeteroES <small>Worker</small></span></a><PreferencesControl /></header><main id="main">
 {!state?.device && <div className="intro"><div><p className="eyebrow">HETEROES / LAB COMPUTE</p><h1>{t('Prepare this computer')}</h1><p>{t('Your GPU stays OFF until you enable it.')}</p></div><Status value={state?.connection ?? 'CONNECTING'}/></div>}
 {!state && <p role="status">{t('Loading…')}</p>}
 {(error === 'WINDOWS_RUNTIME_MISSING' || agent?.startError === 'WINDOWS_RUNTIME_MISSING') && <button className="secondary" onClick={() => void act('external', { target: 'windowsRuntime' })}>{t('Install Windows runtime')}</button>}{agent?.startError && !error && <Alert tone="warning">{t('The local agent is not running. Press Enable contribution to try again.')} {t(explain(agent.startError))} <code>{agent.startError}</code></Alert>}{error && <Alert tone="error">{t(explain(error))} <code>{error}</code></Alert>}
 {!state?.device && <StepHeader steps={['Connect to a lab', 'Sign in', 'GPU and compatibility', 'Pair this device']} current={Math.min(step, 3)}/>}
 {state && !state.device && <div className="onboarding"><section className="panel"><h2>{t(step === 0 ? 'Connect to a lab' : step === 1 ? 'Sign in' : step === 2 ? 'GPU and compatibility' : 'Pair this device')}</h2>
 {(step === 0 || (step === 1 && editLab)) && <form onSubmit={e => { e.preventDefault(); if (!url.trim()) { setError('INVALID_LAB_ADDRESS'); return; } void act('connect', { url }); }}><p>{t('Enter your lab address. If you downloaded this app from your lab\'s website, it is already filled in.')}</p><label>{t('Lab server address')}<input type="text" inputMode="url" autoCapitalize="off" autoCorrect="off" spellCheck={false} placeholder={state.defaultLabUrl || 'lab.example.org'} value={url} onChange={e => setUrl(e.target.value)}/></label><button disabled={!!busy}>{t('Connect')}</button>{editLab && <button type="button" className="secondary" disabled={!!busy} onClick={() => { setEditLab(false); setError(''); }}>{t('Cancel')}</button>}<details className="advanced-panel"><summary>{t('Lab on a private network (Tailscale)')}</summary><div className="secondary-actions"><button type="button" className="secondary" onClick={() => void act('external', { target: 'tailscale' })}>{t('Install or sign in to Tailscale')}</button><button type="button" className="secondary" onClick={() => void act('external', { target: 'help' })}>{t('Network help')}</button></div></details></form>}
 {step === 1 && !editLab && <form onSubmit={e => { e.preventDefault(); void act('login', { username, password }); }}><p className="hint">{t('Connected to')} <code>{state.serverUrl}</code> <button type="button" className="secondary" disabled={!!busy} onClick={() => { setUrl(state.serverUrl); setEditLab(true); setError(''); }}>{t('Change lab')}</button></p><p>{t('Use your own lab account.')}</p><label>{t('Username')}<input autoComplete="username" required value={username} onChange={e => setUsername(e.target.value)}/></label><label>{t('Password')}<input autoComplete="current-password" type="password" required value={password} onChange={e => setPassword(e.target.value)}/></label><button disabled={!!busy}>{t('Sign in')}</button><button className="secondary" type="button" onClick={() => void act('connect', { url })}>{t('Check connection')}</button></form>}
 {step === 2 && <><p>{t('Download an isolated Python runtime, dependencies and the pinned model. No system Python is needed.')}</p><p className="hint">{t('Setup checks disk space and SHA-256. Interrupted downloads resume when you retry.')}</p>{state.setup.profileAvailable === false ? <Alert tone="warning">{t('This development build has no runtime profile. Use the packaged installer.')}</Alert> : <button disabled={!!busy || state.setup.running} onClick={() => void act(state.setup.installed ? 'selftest' : 'install')}>{t(state.setup.installed ? 'Run compatibility check' : 'Install isolated runtime')}</button>}<p className="hint">{t('The check repeats a GPU candidate and verifies 16 answer texts against Linux.')}</p></>}
 {step === 3 && <form onSubmit={e => { e.preventDefault(); void act('pair', { displayName }); }}><label>{t('Device name')}<input maxLength={100} required value={displayName} onChange={e => setDisplayName(e.target.value)} placeholder={t('My GPU computer')}/></label><button disabled={!!busy}>{t('Pair device')}</button><p className="hint">{t('Pairing uses a one-use code from your lab account. An administrator must approve the device.')}</p></form>}
 </section><aside className="panel guide"><span className="guide-icon">↗</span><h2>{t('A few steps. One shared lab.')}</h2><p>{t('Connect, verify your GPU, then choose when to contribute.')}</p><ul><li>{t('A restart always starts with contribution OFF.')}</li><li>{t('Close this window to keep running in the tray.')}</li><li>{t('Stop safely before shutting down this computer.')}</li></ul></aside></div>}
 {!state?.device && <details className="advanced-panel"><summary>{t('Network, role and diagnostics')}</summary>{advanced}</details>}

 {state?.device && <>
 {!state.signedIn && <section className="panel"><h2>{t('Sign in')}</h2><form onSubmit={e => { e.preventDefault(); void act('login', { username, password }); }}><label>{t('Username')}<input required value={username} onChange={e => setUsername(e.target.value)}/></label><label>{t('Password')}<input type="password" required value={password} onChange={e => setPassword(e.target.value)}/></label><button disabled={!!busy}>{t('Sign in')}</button></form>{forgetPairing}</section>}
 <Station view={station!} gauges={stationGauges} gpuName={state.selfTest?.gpuName ?? t('Unknown')} vramGiB={state.selfTest ? (state.selfTest.vramTotalMb / 1024).toFixed(1) + ' GiB VRAM' : ''} deviceName={state.device.displayName} approval={state.device.approvalStatus} busy={!!busy} onToggle={() => void act('contribution', { enabled: station!.toggle.action === 'enable' })}>
 {advanced}
 <div className="desktop-grid"><div className="desktop-stack"><section className="panel"><div className="panel-heading"><h2>{t('Device overview')}</h2><Status value={state.selfTest?.passed?'Ready':'Not yet tested'}/></div><h3 className="gpu-name">{state.selfTest?.gpuName??t('Unknown')}</h3><dl className="desktop-details"><div><dt>{t('VRAM capacity')}</dt><dd>{state.selfTest?((state.selfTest.vramTotalMb)/1024).toFixed(1)+' GiB':'—'}</dd></div><div><dt>{t('Contribution')}</dt><dd><Status value={contribution}/></dd></div><div><dt>{t('Approval')}</dt><dd><Status value={state.device.approvalStatus}/></dd></div><div><dt>{t('Runtime')}</dt><dd>{t(state.setup.installed?'Installed':'Not installed')}</dd></div></dl><details className="desktop-detail"><summary>{t('Device identity')}</summary><p><span className="hint">{t('Worker ID')}</span><code>{state.device.workerId}</code></p><p><span className="hint">{t('Physical GPU UUID')}</span><code>{state.selfTest?.gpuUUID??'—'}</code></p></details><button className="secondary" disabled={!!busy||!!agent?.enabled||agent?.drained===false} onClick={()=>void act('selftest')}>{t('Run compatibility check')}</button></section>
 <section className="panel"><div className="panel-heading"><h2>{t('Assignments')}</h2><span className="hint">{agent?.assignments.length??0}</span></div>{agent?.assignments.length?agent.assignments.map(a=><article className="assignment-card" key={a.assignmentId}><div className="panel-heading"><span className="mono">{a.assignmentId}</span><Status value={a.workerAlive===true?'RUNNING':a.workerAlive===false?'Stopped':'UNKNOWN'}/></div><dl className="desktop-details"><div><dt>{t('Epoch')}</dt><dd>{a.epoch??'—'}</dd></div><div><dt>{t('Worker process')}</dt><dd>{t(a.workerAlive===true?'Alive':a.workerAlive===false?'Confirmed stopped':'Unknown')}</dd></div><div><dt>{t('Coordinator process')}</dt><dd>{t(a.coordinatorAlive===true?'Alive':a.coordinatorAlive===false?'Confirmed stopped':'Unknown')}</dd></div><div><dt>{t('Compute endpoint')}</dt><dd>{t(a.ready?'Ready':'Not ready')}</dd></div></dl></article>):<div className="desktop-empty"><span aria-hidden="true">◇</span><h3>{t('No active assignment')}</h3><p>{t('Experiments assigned to this computer will appear here.')}</p></div>}<p className="hint">{t('Open the lab to inspect generations, candidates, seeds and rewards.')}</p><button className="secondary" disabled={!!busy} onClick={()=>void act('external',{target:'lab'})}>{t('Open lab website')} ↗</button></section>
 <section className="panel"><div className="panel-heading"><h2>{t('Lab connection')}</h2><Status value={state.connection}/></div><CopyValue value={state.serverUrl} label="Copy address"/><dl className="desktop-details"><div><dt>{t('Signed in as')}</dt><dd>{state.session?.user.displayName??t('Signed out')}</dd></div><div><dt>{t('Device name')}</dt><dd>{state.device.displayName}</dd></div></dl><p className="hint">{t('Closing this window keeps Worker in the tray. Use Stop safely before shutting down.')}</p>{forgetPairing}</section></div><aside className="panel monitoring-panel"><ResourceTelemetry observation={state.telemetry} history={state.telemetryHistory} online={state.connection==='ONLINE'}/></aside></div>
 </Station></>}

 {(busy || state?.setup.running) && <section className="panel" role="status"><h3>{t('Progress')}</h3><p>{t(progress?.stage ?? busy)}</p>{progress?.file && <small>{progress.file}</small>}{progress?.total && <><progress max={progress.total} value={progress.received ?? 0}/><p>{Math.round((progress.received ?? 0) / progress.total * 100)}%</p></>}</section>}
 <footer className="desktop-footer"><p className="hint">HeteroES Worker{state?.build ? ' · ' + state.build : ''} · {t('Contribution is your choice.')}</p><button className="secondary" disabled={!!busy} onClick={() => void act('external', { target: 'lab' })}>{t('Open lab website')}</button><button className="secondary" disabled={!!busy} onClick={() => void act('diagnostics')}>{t('Export diagnostics')}</button>{state?.signedIn && <button className="secondary" disabled={!!busy} onClick={() => void act('logout')}>{t('Sign out')}</button>}<button className="secondary" onClick={() => void act('quit')}>{t('Quit safely')}</button></footer>
 </main></div>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><ProductProvider><App /></ProductProvider></React.StrictMode>);
