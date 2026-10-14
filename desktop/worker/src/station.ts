// What the compact "GPU station" shows after pairing, as plain data. Kept free of React so it can be tested.
export type StationAssignment = { assignmentId: string; epoch?: number; ready?: boolean; workerAlive?: boolean | null; coordinatorAlive?: boolean | null };
export type StationInput = {
    signedIn: boolean; device: { approvalStatus: string }; connection: string; nowSeconds: number;
    agent: { enabled: boolean; drained: boolean; error?: string; startError?: string; assignments: StationAssignment[] } | null | undefined;
    telemetry: Telemetry | null | undefined;
};
export type Telemetry = { sampledAt: number; receivedAt?: number; gpu?: { utilizationPercent?: number | null; vramUsedMb?: number | null; vramTotalMb?: number | null; temperatureC?: number | null } | null };
export type Mode = 'off' | 'ready' | 'working' | 'draining' | 'unknown';
export type Gauge = { key: 'gpu' | 'vram' | 'temp'; label: string; percent: number | null; text: string };
export type StationView = {
    mode: Mode; headline: string; detail: string;
    toggle: { action: 'enable' | 'stop'; label: string; disabled: boolean };
    blocker: 'approval' | 'sign-in' | 'agent' | null;
    assignments: { id: string; epoch?: number; ready?: boolean }[];
};

const FRESH_SECONDS = 30;

export function stationView(input: StationInput): StationView {
    const agent = input.agent;
    const unknown = Boolean(agent?.error) || Boolean(agent?.assignments.some(a => a.workerAlive === null || a.coordinatorAlive === null));
    const working = Boolean(agent?.assignments.some(a => a.workerAlive === true));
    const mode: Mode = unknown ? 'unknown' : agent?.enabled ? (working ? 'working' : 'ready') : agent && agent.drained === false ? 'draining' : 'off';
    const approved = input.device.approvalStatus === 'APPROVED';
    const stopping = mode === 'ready' || mode === 'working';
    let blocker: StationView['blocker'] = null;
    if (!stopping) blocker = !approved ? 'approval' : !input.signedIn ? 'sign-in' : !agent ? 'agent' : null;
    const copy: Record<Mode, [string, string]> = {
        off: ['Contribution is OFF', 'No GPU work is running.'],
        ready: ['Ready to contribute', 'Waiting for the lab to hand out work.'],
        working: ['Your GPU is working', 'Your worker is evaluating a candidate.'],
        draining: ['Waiting for owned processes to stop.', 'Do not shut this computer down yet.'],
        unknown: ['A process state is unknown; resources remain reserved.', 'Process ownership is unknown. Check diagnostics before shutting down.'],
    };
    return {
        mode, headline: copy[mode][0], detail: copy[mode][1], blocker,
        toggle: { action: stopping || mode === 'unknown' || mode === 'draining' ? 'stop' : 'enable', label: stopping || mode === 'unknown' || mode === 'draining' ? 'Stop safely' : 'Enable contribution', disabled: mode === 'draining' || (!stopping && mode !== 'unknown' && blocker !== null) },
        assignments: (agent?.assignments ?? []).filter(a => a.workerAlive !== false).map(a => ({ id: a.assignmentId, epoch: a.epoch, ready: a.ready })),
    };
}

const pct = (value: number) => Math.max(0, Math.min(100, Math.round(value)));

/** GPU load, VRAM and temperature as bars; a measurement older than 30 s is shown as unknown, not as its last value. */
export function gauges(telemetry: Telemetry | null | undefined, nowSeconds: number): Gauge[] {
    const fresh = telemetry && nowSeconds - (telemetry.receivedAt ?? telemetry.sampledAt) <= FRESH_SECONDS ? telemetry.gpu : null;
    const util = fresh?.utilizationPercent, used = fresh?.vramUsedMb, total = fresh?.vramTotalMb, temp = fresh?.temperatureC;
    const known = (v: number | null | undefined): v is number => typeof v === 'number' && Number.isFinite(v);
    return [
        { key: 'gpu', label: 'GPU load', percent: known(util) ? pct(util) : null, text: known(util) ? `${pct(util)} %` : '—' },
        { key: 'vram', label: 'VRAM', percent: known(used) && known(total) && total > 0 ? pct(100 * used / total) : null, text: known(used) && known(total) && total > 0 ? `${(used / 1024).toFixed(1)} / ${(total / 1024).toFixed(1)} GiB` : '—' },
        { key: 'temp', label: 'Temperature', percent: known(temp) ? pct(temp) : null, text: known(temp) ? `${Math.round(temp)} °C` : '—' },
    ];
}
