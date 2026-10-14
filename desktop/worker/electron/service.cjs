const fs = require('node:fs');
const fsp = fs.promises;
const path = require('node:path');
const crypto = require('node:crypto');
const net = require('node:net');
const os = require('node:os');
const { addresses, qualified, computeConfig } = require('./network.cjs');
const { Setup } = require('./setup.cjs');
// Say who we are: a public edge such as Cloudflare blocks anonymous client signatures.
const AGENT = { 'User-Agent': 'HeteroES-Worker/0.1' };
const { Bridge } = require('./bridge.cjs');
const PRIVATE_HOST = /^10\.|^192\.168\.|^127\.|^172\.(1[6-9]|2\d|3[01])\.|^100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\./;
const isPrivateHost = host => host === 'localhost' || net.isIP(host) && (host === '::1' || PRIVATE_HOST.test(host));
// Accept what people type or paste ("lab.example.org", "https://lab.example.org/#downloads") and keep only the origin.
function serverAddress(value) {
    const text = typeof value === 'string' ? value.trim() : '';
    if (!text || /\s/.test(text)) throw Error('INVALID_LAB_ADDRESS');
    let url;
    try {
        if (/^[a-z][a-z0-9+.-]*:\/\//i.test(text)) url = new URL(text);
        else { const host = new URL('https://' + text).hostname.replace(/^\[|\]$/g, ''); url = new URL((isPrivateHost(host) ? 'http://' : 'https://') + text); }
    } catch { throw Error('INVALID_LAB_ADDRESS'); }
    if (url.username || url.password || url.search) throw Error('INVALID_LAB_ADDRESS');
    if (url.protocol !== 'https:' && !(url.protocol === 'http:' && isPrivateHost(url.hostname.replace(/^\[|\]$/g, '')))) throw Error('HTTPS_OR_PRIVATE_NETWORK_REQUIRED');
    return url.origin;
}
// Build-time defaults (offered lab address, build name) shipped next to the runtime; anything unusable is ignored.
function readDefaults(resources) {
    try {
        const file = JSON.parse(fs.readFileSync(path.join(resources, 'defaults.json'), 'utf8'));
        let labUrl = '';
        try { labUrl = typeof file.labUrl === 'string' ? serverAddress(file.labUrl) : ''; } catch { }
        return { labUrl, build: /^[A-Za-z0-9._-]{1,40}$/.test(file.build ?? '') ? file.build : '' };
    } catch { return { labUrl: '', build: '' }; }
}
const SAFE_CODE = /^[A-Z][A-Z0-9_]+$/;
// After a failed start, the window's own polling waits this long before trying again; pressing Enable never waits.
const RETRY_MS = 30000;
class Service {
    constructor(root, resources, vault, options = {}) { this.root = root; this.vault = vault; this.fetch = options.fetch ?? fetch; this.setup = options.setup ?? new Setup(root, resources); this.makeBridge = options.makeBridge ?? ((...args) => new Bridge(...args)); this.platform = options.platform ?? process.platform; this.interfaces = options.interfaces ?? os.networkInterfaces; this.settingsPath = path.join(root, 'settings.json'); this.settings = fs.existsSync(this.settingsPath) ? JSON.parse(fs.readFileSync(this.settingsPath, 'utf8')) : {}; this.userToken = ''; this.session = null; this.bridge = null; this.selfTest = this.settings.selfTest ?? null; this.device = this.settings.device ?? null; this.lastState = null; this.connection = 'OFFLINE'; this.autoStart = true; this.attempts = new Set(); this.defaults = readDefaults(resources); this.log = options.log ?? { info() { }, detail() { }, error() { } }; this.now = options.now ?? Date.now; this.agentFailure = null; this.loggedFailure = ''; this.retryAt = 0; }
    // The agent is known to be gone (it never started or it ended). Say why in the log, once per distinct cause, and
    // keep only the code for the window. The raw text of stderr never leaves the log file.
    recordAgentFailure(error, bridge) {
        const failure = bridge?.failure?.() ?? {};
        const code = SAFE_CODE.test(error?.message ?? '') ? error.message : (failure.code ?? 'AGENT_EXITED');
        this.agentFailure = { code };
        this.retryAt = this.now() + RETRY_MS;
        const key = [code, failure.exitCode, failure.spawnCode].join('|');
        if (key === this.loggedFailure) return;
        this.loggedFailure = key;
        let lab = '';
        try { lab = new URL(this.settings.serverUrl).hostname; } catch { }
        this.log.info('agent failed', { code, exitCode: failure.exitCode ?? '', exitHex: Number.isInteger(failure.exitCode) ? '0x' + (failure.exitCode >>> 0).toString(16) : '', signal: failure.signal ?? '', spawnCode: failure.spawnCode ?? '', lab });
        if (failure.stderrTail) this.log.detail('agent stderr', failure.stderrTail);
    }
    computeProfile(value = this.settings.compute) {
        return computeConfig(value, this.selfTest, this.platform, addresses(this.interfaces()));
    }
    advertisedProfile(compute = this.computeProfile()) { return this.selfTest ? { ...this.selfTest, coordinator: compute.coordinator } : undefined; }
    async configureCompute(value) {
        if (this.setup.running) throw Error('SETUP_IN_PROGRESS');
        const compute = this.computeProfile(value);
        if (this.device) {
            if (!this.userToken) throw Error('SIGN_IN_REQUIRED');
            if (!this.bridge && !this.settings.computePending) await this.startAgent();
            if (this.bridge) {
                const state = await this.bridge.call('status');
                if (state.enabled || !state.drained) throw Error('STOP_WORK_FIRST');
            }
            const health = await this.api('/api/v1/health', undefined, '');
            if (!health.deviceConfiguration) throw Error('LAB_UPDATE_REQUIRED');
            const stopped = await this.quit();
            if (!stopped.drained) throw Error('DRAIN_NOT_CONFIRMED');
            const previous = { ...this.settings };
            this.settings.computePending = compute;
            try { await this.save(); }
            catch (error) { this.settings = previous; throw error; }
            try {
                await this.api('/api/v1/devices/' + this.device.deviceId + '/configuration', {
                    computeUrl: `http://${compute.host}:8765`, selfTest: this.advertisedProfile(compute),
                }, this.userToken, 'PATCH');
            } catch (error) {
                // A lost reply may mean the server committed. Keep a durable
                // pending record and stay stopped until the owner retries.
                if (!previous.computePending && /^LAB_HTTP_(400|401|403|404|409|422)$/.test(error.message)) {
                    this.settings = previous;
                    await this.save();
                    await this.startAgent();
                }
                throw error;
            }
        }
        this.settings.compute = compute;
        delete this.settings.computePending;
        await this.save();
        if (this.device) await this.startAgent();
        return compute;
    }
    async save() { await fsp.mkdir(this.root, { recursive: true, mode: 0o700 }); const temporary = this.settingsPath + '.tmp'; await fsp.writeFile(temporary, JSON.stringify(this.settings, null, 2), { mode: 0o600 }); await fsp.rename(temporary, this.settingsPath); }
    // One bounded network call. Reads and sign-in can be cancelled by Quit; writes that create credentials never are.
    async guarded(work, cancellable) {
        const attempt = { controller: new AbortController(), cancelled: false };
        const timer = setTimeout(() => attempt.controller.abort(), 15000);
        if (cancellable) this.attempts.add(attempt);
        try { return await work(attempt.controller.signal); }
        catch (error) {
            if (attempt.cancelled) throw Error('ACTION_CANCELLED');
            if (error?.name === 'AbortError') throw Error('LAB_TIMEOUT');
            throw SAFE_CODE.test(error?.message ?? '') ? error : Error('LAB_UNREACHABLE');
        }
        finally { clearTimeout(timer); this.attempts.delete(attempt); }
    }
    abortPending() { for (const attempt of this.attempts) { attempt.cancelled = true; attempt.controller.abort(); } }
    async api(route, body, token = this.userToken, method) {
        method ??= body === undefined ? 'GET' : 'POST';
        try {
            const data = await this.guarded(async signal => {
                const response = await this.fetch(this.settings.serverUrl + route, { method, headers: { ...AGENT, 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) }, body: body === undefined ? undefined : JSON.stringify(body), signal });
                if (!response.ok) throw Error('LAB_HTTP_' + response.status);
                if (response.status === 204) return null;
                try { return await response.json(); } catch (error) { if (signal.aborted) throw error; throw Error('LAB_BAD_RESPONSE'); }
            }, method === 'GET' || route === '/api/v1/auth/login');
            this.connection = 'ONLINE';
            return data;
        }
        catch (error) {
            this.connection = 'OFFLINE';
            throw error;
        }
    }
    async connect(url) {
        const target=serverAddress(url);
        let health;
        try {
            health=await this.guarded(async signal=>{
                const response=await this.fetch(target+'/api/v1/health',{headers:AGENT,signal});
                if(!response.ok)throw Error('LAB_HTTP_'+response.status);
                let body;
                try{body=await response.json();}catch(error){if(signal.aborted)throw error;throw Error('NOT_A_LAB');}
                if(!body||typeof body!=='object'||Array.isArray(body))throw Error('NOT_A_LAB');
                return body;
            },true);
        } catch(error) {
            if(!this.settings.serverUrl||target===this.settings.serverUrl)this.connection='OFFLINE';
            throw error;
        }
        if(!health.agentMode)throw Error('LAB_AGENT_MODE_REQUIRED');
        if(this.device && target!==this.settings.serverUrl){
            let expected=this.settings.serverInstanceId;
            if(!expected){const previous=await this.api('/api/v1/health');expected=previous.serverInstanceId;}
            if(!expected || health.serverInstanceId!==expected)throw Error('DIFFERENT_LAB_REQUIRES_NEW_PAIRING');
        }
        if(this.bridge){
            const state=await this.bridge.call('status');
            if(state.enabled || !state.drained)throw Error('STOP_WORK_FIRST');
            const result=await this.quit();if(!result.drained)throw Error('DRAIN_NOT_CONFIRMED');
        }
        this.settings.serverUrl=target;this.settings.serverInstanceId=health.serverInstanceId;
        this.settings.uiUrl=health.uiUrl?serverAddress(health.uiUrl):target;
        this.userToken='';this.session=null;await this.save();this.connection='ONLINE';
        if(this.device)await this.startAgent();
        return health;
    }
    async login(username, password) { if (!this.settings.serverUrl)
        throw Error('SELECT_LAB_FIRST'); const session = await this.api('/api/v1/auth/login', { username, password }, ''); this.userToken = session.accessToken; const { accessToken, ...publicSession } = session; this.session = publicSession; this.autoStart = true; return publicSession; }
    async checkConnection() {
        const checks = [], report = { checks, assignments: [] };
        try {
            if (!this.settings.serverUrl) throw Error('SELECT_LAB_FIRST');
            const health = await this.api('/api/v1/health', undefined, '');
            if (!health.ok || !health.agentMode) throw Error('LAB_AGENT_MODE_REQUIRED');
            if (this.settings.serverInstanceId && health.serverInstanceId !== this.settings.serverInstanceId)
                throw Error('DIFFERENT_LAB_REQUIRES_NEW_PAIRING');
            checks.push({ step: 'lab', status: 'PASS', code: 'LAB_REACHABLE' });
        } catch (error) {
            checks.push({ step: 'lab', status: 'FAIL', code: /^[A-Z][A-Z0-9_]+$/.test(error.message) ? error.message : 'LAB_UNREACHABLE' });
        }
        if (this.bridge) {
            try { report.assignments = (await this.bridge.call('check_connection')).assignments; }
            catch (error) { checks.push({ step: 'coordinator', status: 'FAIL', code: SAFE_CODE.test(error.message) ? error.message : 'AGENT_CHECK_FAILED' }); }
        }
        else if (this.device && this.agentFailure) checks.push({ step: 'coordinator', status: 'FAIL', code: this.agentFailure.code });
        if (!report.assignments.length) for (const step of ['coordinator', 'bulk'])
            if (!checks.some(c => c.step === step)) checks.push({ step, status: 'SKIP', code: 'NO_ASSIGNMENT' });
        return report;
    }
    async startAgent() { if (this.settings.computePending) throw Error('COMPUTE_CHANGE_PENDING'); this.autoStart = true; if (this.bridge)
        return; if (!this.device)
        throw Error('DEVICE_NOT_PAIRED'); const token = await this.vault.read('device-token'); if (!token)
        throw Error('DEVICE_CREDENTIAL_UNAVAILABLE'); const compute = this.computeProfile(); const p = this.setup.paths(); const config = path.join(this.root, 'agent-config.json'); const workerId = this.device.workerId; await fsp.writeFile(config, JSON.stringify({ serverUrl: this.settings.serverUrl, deviceId: this.device.deviceId, workerId, stateDirectory: path.join(this.root, 'agent-state'), modelPath: p.model, computeUrl: `http://${compute.host}:8765`, workerHost: compute.host, workerPort: 8765, workerOnly: !compute.coordinator, largeDataDirectory: this.setup.storage?.artifacts, storageVolumeUUID: this.setup.storage?.volumeUUID, selfTest: this.advertisedProfile(compute) }), { mode: 0o600 }); this.bridge = this.makeBridge(p.python, p.source, config, token); try {
        await this.bridge.ready;
        if(this.selfTest?.recipeVersions?.includes(2)){
            const health=await this.api('/api/v1/health',undefined,'');
            if(health.recipeVersions?.includes(2)){
                for(let attempt=0;attempt<20;attempt++){
                    const state=await this.bridge.call('status');
                    try{
                        await this.api('/api/v1/device/qualification',{bootId:state.bootId,selfTest:this.advertisedProfile(compute)},token,'PATCH');break;
                    }catch(error){
                        if(error.message!=='LAB_HTTP_409'||attempt===19)throw error;
                        await new Promise(resolve=>setTimeout(resolve,200));
                    }
                }
            }
        }
        this.agentFailure = null; this.loggedFailure = '';
    }
    catch (error) {
        const failed = this.bridge;
        // A child that never started or has already ended owns nothing: release it, so Enable can try again.
        if (failed.exited?.()) { if (this.bridge === failed) this.bridge = null; this.recordAgentFailure(error, failed); throw error; }
        try { if ((await failed.call('quit')).drained && this.bridge === failed) this.bridge = null; }
        catch { /* Retain uncertain process ownership for the next safe Quit. */ }
        throw error;
    } }
    async pair(displayName) { if (!this.selfTest?.passed)
        throw Error('SELF_TEST_REQUIRED'); if (!this.userToken)
        throw Error('SIGN_IN_REQUIRED'); if (!this.vault.available())
        throw Error('SECURE_STORAGE_REQUIRED'); if (this.device)
        throw Error('ALREADY_PAIRED'); const compute = this.computeProfile(); const code = await this.api('/api/v1/devices/pairing-codes', {}); const workerId = 'desktop-' + crypto.randomUUID().replaceAll('-', '').slice(0, 12); const device = await this.api('/api/v1/device/enroll', { code: code.code, workerId, displayName: displayName.trim() || 'GPU Worker', computeUrl: `http://${compute.host}:8765`, selfTest: this.advertisedProfile(compute) }, ''); await this.vault.write('device-token', device.deviceToken); const { deviceToken, ...publicDevice } = device; this.device = publicDevice; this.settings = { ...this.settings, device: publicDevice, selfTest: this.selfTest }; await this.save(); await this.startAgent(); return publicDevice; }
    async contribution(enabled) { if (!this.bridge) {
        if (!enabled) return { enabled: false, drained: true };
        // Paired but the agent is not running (it failed to start earlier): try again now and report the real code.
        if (!this.device) throw Error('AGENT_UNAVAILABLE');
        await this.startAgent();
    } if (!enabled)
        await this.bridge.call('off'); if (!this.userToken) {
        if (!enabled)
            return this.bridge.call('status');
        throw Error('SIGN_IN_REQUIRED');
    } const state = await this.bridge.call('status'); return this.api('/api/v1/devices/' + this.device.deviceId + '/contribution', { enabled, bootId: state.bootId }); }
    async status() {
        if (this.autoStart && this.device && this.setup.status().installed && !this.bridge && this.now() >= this.retryAt)
            try {
                await this.startAgent();
            }
            catch {
                this.lastState = { drained: false, enabled: false, error: this.settings.computePending ? 'COMPUTE_CHANGE_PENDING' : 'AGENT_UNAVAILABLE' };
            }
        if (!this.bridge && this.agentFailure) this.lastState = { drained: true, enabled: false, startError: this.agentFailure.code };
        if (this.bridge)
            try {
                this.lastState = await this.bridge.call('status');
            }
            catch (error) {
                const dead = this.bridge;
                if (dead.exited?.()) { this.bridge = null; this.recordAgentFailure(error, dead); this.lastState = { drained: true, enabled: false, startError: this.agentFailure.code }; }
                else this.lastState = { drained: false, enabled: false, error: 'AGENT_UNAVAILABLE' };
            }
        if (this.userToken && this.device)
            try {
                const devices = await this.api('/api/v1/devices');
                const current = devices.find(d => d.deviceId === this.device.deviceId);
                if (current)
                    this.device = { ...this.device, ...current };
            }
            catch { }
        const p = this.lastState;
        return { compute: { pending: !!this.settings.computePending, ...(this.settings.compute ?? { network: 'lan', coordinator: false, host: '127.0.0.1' }), eligible: qualified(this.selfTest, this.platform), addresses: addresses(this.interfaces()) }, serverUrl: this.settings.serverUrl ?? '', defaultLabUrl: this.defaults.labUrl, build: this.defaults.build, signedIn: !!this.userToken, session: this.session, device: this.device, selfTest: this.selfTest, setup: this.setup.status(), telemetry: p?.telemetry ?? null, telemetryHistory:p?.telemetryHistory??[], connection: p?.connection?.status ?? this.connection, agent: p ? { bootId: p.bootId, enabled: !!p.enabled, drained: p.drained, error: p.error, startError: p.startError, assignments: (p.processes ?? []).map(r => ({ assignmentId: r.assignmentId, epoch:r.epoch, workerAlive: r.workerAlive, coordinatorAlive: r.coordinatorAlive, ready: r.ready })) } : null };
    }
    async quit() { this.autoStart = false; if (this.setup.running)
        throw Error('SETUP_IN_PROGRESS'); this.abortPending(); if (!this.bridge)
        return { drained: true }; try {
        await this.contribution(false);
    }
    catch {
        await this.bridge.call('off');
    } const result = await this.bridge.call('quit'); if (result.drained)
        this.bridge = null; return result; }
    async logout() { const drained = await this.quit(); if (!drained.drained)
        throw Error('DRAIN_NOT_CONFIRMED'); if (this.userToken)
        try {
            await this.api('/api/v1/auth/logout', {});
        }
        catch { } this.userToken = ''; this.session = null; return { ok: true }; }
    async selftest() { if (this.bridge) {
        const state = await this.bridge.call('status');
        if (!state.drained || state.enabled)
            throw Error('STOP_WORK_FIRST');
    } if (this.bridge) await this.quit(); this.selfTest = await this.setup.selfTest(); this.settings.selfTest = this.selfTest; await this.save(); if (this.device) await this.startAgent(); return this.selfTest; }
}
module.exports = { Service, serverAddress };
