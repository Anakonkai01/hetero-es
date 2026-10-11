import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ProductProvider, PreferencesControl, StepHeader, Status, Alert, useProduct } from '@heteroes/product-ui';
import '@heteroes/product-ui/theme.css';
import './style.css';
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
    serverUrl: string;
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
    };
    setup: SetupState;
    agent?: {
        enabled: boolean;
        drained: boolean;
        error?: string;
        assignments: {
            assignmentId: string;
            workerAlive: boolean | null;
            coordinatorAlive: boolean | null;
        }[];
    };
};
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
function App() {
    const { t } = useProduct();
    const [state, setState] = useState<State>();
    const [url, setUrl] = useState('');
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [displayName, setDisplayName] = useState('');
    const [error, setError] = useState('');
    const [busy, setBusy] = useState('');
    const polling = useRef(false);
    const quitting = useRef(false);
    async function refresh() { if (polling.current || quitting.current)
        return; polling.current = true; try {
        const row = await window.worker.call('status');
        if (row.ok) {
            const s = row.result as State;
            setState(s);
            setUrl(old => old || s.serverUrl);
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
    return <div className="desktop-shell"><header className="desktop-header"><a className="brand" href="#main">H<span>HeteroES Worker</span></a><PreferencesControl /></header><main id="main">
 <div className="intro"><div><p className="eyebrow">HETEROES / LAB COMPUTE</p><h1>{t(state?.device ? 'Share your GPU with your research lab.' : 'Prepare this computer')}</h1><p>{t('Your GPU stays OFF until you enable it.')}</p></div><Status value={state?.connection ?? 'CONNECTING'}/></div>
 {!state && <p role="status">{t('Loading…')}</p>}
 {error === 'WINDOWS_RUNTIME_MISSING' && <button className="secondary" onClick={() => void act('external', { target: 'windowsRuntime' })}>{t('Install Windows runtime')}</button>}{error && <Alert tone="error">{t(explanations[error] ?? 'Could not complete the action. Check the connection and export diagnostics.')} <code>{error}</code></Alert>}
 {!state?.device && <StepHeader steps={['Connect to a lab', 'Sign in', 'GPU and compatibility', 'Pair this device']} current={Math.min(step, 3)}/>}
 {state && !state.device && <div className="onboarding"><section className="panel"><h2>{t(step === 0 ? 'Connect to a lab' : step === 1 ? 'Sign in' : step === 2 ? 'GPU and compatibility' : 'Pair this device')}</h2>
 {step === 0 && <form onSubmit={e => { e.preventDefault(); void act('connect', { url }); }}><p>{t('Select your lab and sign in to begin.')}</p><label>{t('Lab server address')}<input type="url" required placeholder="http://100.x.x.x:8002" value={url} onChange={e => setUrl(e.target.value)}/></label><button disabled={!!busy}>{t('Check connection')}</button><p className="hint">{t('No terminal commands are required.')}</p><div className="secondary-actions"><button type="button" className="secondary" onClick={() => void act('external', { target: 'tailscale' })}>{t('Install or sign in to Tailscale')}</button><button type="button" className="secondary" onClick={() => void act('external', { target: 'help' })}>{t('Network help')}</button></div></form>}
 {step === 1 && <form onSubmit={e => { e.preventDefault(); void act('login', { username, password }); }}><p>{t('Use your own lab account.')}</p><label>{t('Username')}<input autoComplete="username" required value={username} onChange={e => setUsername(e.target.value)}/></label><label>{t('Password')}<input autoComplete="current-password" type="password" required value={password} onChange={e => setPassword(e.target.value)}/></label><button disabled={!!busy}>{t('Sign in')}</button><button className="secondary" type="button" onClick={() => void act('connect', { url })}>{t('Check connection')}</button></form>}
 {step === 2 && <><p>{t('Download an isolated Python runtime, dependencies and the pinned model. No system Python is needed.')}</p><p className="hint">{t('Setup checks disk space and SHA-256. Interrupted downloads resume when you retry.')}</p>{state.setup.profileAvailable === false ? <Alert tone="warning">{t('This development build has no runtime profile. Use the packaged installer.')}</Alert> : <button disabled={!!busy || state.setup.running} onClick={() => void act(state.setup.installed ? 'selftest' : 'install')}>{t(state.setup.installed ? 'Run compatibility check' : 'Install isolated runtime')}</button>}<p className="hint">{t('The check repeats a GPU candidate and verifies 16 answer texts against Linux.')}</p></>}
 {step === 3 && <form onSubmit={e => { e.preventDefault(); void act('pair', { displayName }); }}><label>{t('Device name')}<input maxLength={100} required value={displayName} onChange={e => setDisplayName(e.target.value)} placeholder={t('My GPU computer')}/></label><button disabled={!!busy}>{t('Pair device')}</button><p className="hint">{t('Pairing uses a one-use code from your lab account. An administrator must approve the device.')}</p></form>}
 </section><aside className="panel guide"><span className="guide-icon">↗</span><h2>{t('A few steps. One shared lab.')}</h2><p>{t('Connect, verify your GPU, then choose when to contribute.')}</p><ul><li>{t('A restart always starts with contribution OFF.')}</li><li>{t('Close this window to keep running in the tray.')}</li><li>{t('Stop safely before shutting down this computer.')}</li></ul></aside></div>}
 {state?.device && <><section className="panel contribution"><div><p className="eyebrow">{state.device.displayName}</p><h2>{t(contribution === 'ON' ? 'Ready to contribute' : contribution === 'DRAINING' ? 'Waiting for owned processes to stop.' : contribution === 'UNKNOWN' ? 'A process state is unknown; resources remain reserved.' : 'Contribution is OFF')}</h2><p>{t(!approval ? 'Waiting for administrator approval.' : active ? 'Your worker is evaluating a candidate.' : 'No GPU work is running.')}</p></div><Status value={contribution}/><button disabled={!!busy || (!agent?.enabled && (!approval || !state.signedIn || !!unknown || contribution === 'DRAINING'))} onClick={() => void act('contribution', { enabled: !agent?.enabled })}>{t(agent?.enabled ? 'Stop safely' : 'Enable contribution')}</button></section>
 {!state.signedIn && <section className="panel"><h2>{t('Sign in')}</h2><form onSubmit={e => { e.preventDefault(); void act('login', { username, password }); }}><label>{t('Username')}<input required value={username} onChange={e => setUsername(e.target.value)}/></label><label>{t('Password')}<input type="password" required value={password} onChange={e => setPassword(e.target.value)}/></label><button disabled={!!busy}>{t('Sign in')}</button></form></section>}
 <div className="metrics"><section className="panel"><p className="eyebrow">{t('GPU and compatibility')}</p><h3>{state.selfTest?.gpuName ?? t('Unknown')}</h3><p>{((state.selfTest?.vramTotalMb ?? 0) / 1024).toFixed(1)} GiB</p><Status value={state.selfTest?.passed ? 'Ready' : 'Not yet tested'}/></section><section className="panel"><p className="eyebrow">{t('Current job')}</p><h3>{agent?.assignments.length ?? 0} {t('Assignments')}</h3><p>{agent?.assignments[0]?.assignmentId ?? t('No active assignment')}</p></section><section className="panel"><p className="eyebrow">{t('Network')}</p><Status value={state.connection}/><p>{state.serverUrl}</p><Status value={state.device.approvalStatus}/></section></div></>}
 {(busy || state?.setup.running) && <section className="panel" role="status"><h3>{t('Progress')}</h3><p>{t(progress?.stage ?? busy)}</p>{progress?.file && <small>{progress.file}</small>}{progress?.total && <><progress max={progress.total} value={progress.received ?? 0}/><p>{Math.round((progress.received ?? 0) / progress.total * 100)}%</p></>}</section>}
 <footer className="desktop-footer"><button className="secondary" disabled={!!busy} onClick={() => void act('external', { target: 'lab' })}>{t('Open lab website')}</button><button className="secondary" disabled={!!busy} onClick={() => void act('diagnostics')}>{t('Export diagnostics')}</button>{state?.signedIn && <button className="secondary" disabled={!!busy} onClick={() => void act('logout')}>{t('Sign out')}</button>}<button className="secondary" disabled={!!busy} onClick={() => void act('quit')}>{t('Quit safely')}</button></footer>
 </main></div>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><ProductProvider><App /></ProductProvider></React.StrictMode>);
