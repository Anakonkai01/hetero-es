import { useEffect, useRef, useState } from 'react';
import type { ConnectionReport, State } from './workerState';
export function useWorkerApp() {
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
  async function refresh() {
    if (polling.current || quitting.current) return;
    polling.current = true;
    try {
      const row = await window.worker.call('status');
      if (row.ok) {
        const s = row.result as State;
        setState(s);
        setUrl((old) => old || s.serverUrl || s.defaultLabUrl || '');
      } else setError(row.error ?? 'ACTION_FAILED');
    } catch {
      setError('AGENT_UNAVAILABLE');
    } finally {
      polling.current = false;
    }
  }
  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 3000);
    return () => clearInterval(timer);
  }, []);
  async function act(action: string, args: Record<string, unknown> = {}) {
    setBusy(action);
    setError('');
    try {
      const row = await window.worker.call(action, args);
      if (!row.ok) {
        setError(row.error ?? 'ACTION_FAILED');
        return;
      }
      if (action === 'login') setPassword('');
      if (action === 'checkConnection') setConnectionReport(row.result as ConnectionReport);
      if (action === 'configureCompute' || action === 'connect') setConnectionReport(undefined);
      if (action === 'forgetDevice') {
        setConnectionReport(undefined);
        setConfirmForget(false);
        setUrl(state?.defaultLabUrl ?? '');
      }
      if (action === 'connect') setEditLab(false);
      if (action === 'quit') {
        if (
          (
            row.result as {
              drained: boolean;
            }
          ).drained
        )
          quitting.current = true;
        else setError('DRAIN_NOT_CONFIRMED');
      }
      await refresh();
    } catch {
      setError('ACTION_FAILED');
    } finally {
      setBusy('');
    }
  }

  return {
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
  };
}
