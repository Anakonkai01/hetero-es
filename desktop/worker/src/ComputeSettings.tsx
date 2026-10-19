import { Alert,useProduct } from '@heteroes/product-ui';
import { useState } from 'react';
import type { State } from './workerState';
export function ComputeSettings({ state, busy, act }: { state: State; busy: string; act: (action: string, args?: Record<string, unknown>) => Promise<void> }) {
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
