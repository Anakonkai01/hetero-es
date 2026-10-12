const fs = require('node:fs');
const fsp = fs.promises;
const path = require('node:path');
const crypto = require('node:crypto');
const net = require('node:net');
const { Setup } = require('./setup.cjs');
const { Bridge } = require('./bridge.cjs');
function serverAddress(value) { const url = new URL(value); if (url.username || url.password || url.search || url.hash || !['', '/'].includes(url.pathname))
    throw Error('INVALID_LAB_ADDRESS'); const host = url.hostname.replace(/^\[|\]$/g, ''); const privateAddress = host === 'localhost' || net.isIP(host) && (host === '::1' || /^10\.|^192\.168\.|^127\.|^172\.(1[6-9]|2\d|3[01])\.|^100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\./.test(host)); if (url.protocol !== 'https:' && !(url.protocol === 'http:' && privateAddress))
    throw Error('HTTPS_OR_PRIVATE_NETWORK_REQUIRED'); return url.origin; }
class Service {
    constructor(root, resources, vault, options = {}) { this.root = root; this.vault = vault; this.fetch = options.fetch ?? fetch; this.setup = options.setup ?? new Setup(root, resources); this.makeBridge = options.makeBridge ?? ((...args) => new Bridge(...args)); this.settingsPath = path.join(root, 'settings.json'); this.settings = fs.existsSync(this.settingsPath) ? JSON.parse(fs.readFileSync(this.settingsPath, 'utf8')) : {}; this.userToken = ''; this.session = null; this.bridge = null; this.selfTest = this.settings.selfTest ?? null; this.device = this.settings.device ?? null; this.lastState = null; this.connection = 'OFFLINE'; this.autoStart = true; }
    async save() { await fsp.mkdir(this.root, { recursive: true, mode: 0o700 }); await fsp.writeFile(this.settingsPath, JSON.stringify(this.settings, null, 2), { mode: 0o600 }); }
    async api(route, body, token = this.userToken, method) { const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 15000); try {
        const response = await this.fetch(this.settings.serverUrl + route, { method: method ?? (body === undefined ? 'GET' : 'POST'), headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) }, body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal });
        if (!response.ok)
            throw Error('LAB_HTTP_' + response.status);
        this.connection = 'ONLINE';
        return response.status === 204 ? null : await response.json();
    }
    catch (error) {
        this.connection = 'OFFLINE';
        throw error;
    }
    finally {
        clearTimeout(timer);
    } }
    async connect(url) {
        const target=serverAddress(url);
        const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),15000);
        let health;
        try {
            const response=await this.fetch(target+'/api/v1/health',{signal:controller.signal});
            if(!response.ok)throw Error('LAB_HTTP_'+response.status);
            health=await response.json();
        } finally {clearTimeout(timer);}
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
        this.userToken='';this.session=null;await this.save();
        if(this.device)await this.startAgent();
        return health;
    }
    async login(username, password) { if (!this.settings.serverUrl)
        throw Error('SELECT_LAB_FIRST'); const session = await this.api('/api/v1/auth/login', { username, password }, ''); this.userToken = session.accessToken; const { accessToken, ...publicSession } = session; this.session = publicSession; return publicSession; }
    async startAgent() { this.autoStart = true; if (this.bridge)
        return; if (!this.device)
        throw Error('DEVICE_NOT_PAIRED'); const token = await this.vault.read('device-token'); if (!token)
        throw Error('DEVICE_CREDENTIAL_UNAVAILABLE'); const p = this.setup.paths(); const config = path.join(this.root, 'agent-config.json'); const workerId = this.device.workerId; await fsp.writeFile(config, JSON.stringify({ serverUrl: this.settings.serverUrl, deviceId: this.device.deviceId, workerId, stateDirectory: path.join(this.root, 'agent-state'), modelPath: p.model, computeUrl: 'http://127.0.0.1:8765', workerHost: '127.0.0.1', workerPort: 8765, workerOnly: true, largeDataDirectory: this.setup.storage?.artifacts, storageVolumeUUID: this.setup.storage?.volumeUUID, selfTest: this.selfTest ? { ...this.selfTest, coordinator: false } : undefined }), { mode: 0o600 }); this.bridge = this.makeBridge(p.python, p.source, config, token); try {
        await this.bridge.ready;
        if(this.selfTest?.recipeVersions?.includes(2)){
            const health=await this.api('/api/v1/health',undefined,'');
            if(health.recipeVersions?.includes(2)){
                for(let attempt=0;attempt<20;attempt++){
                    const state=await this.bridge.call('status');
                    try{
                        await this.api('/api/v1/device/qualification',{bootId:state.bootId,selfTest:{...this.selfTest,coordinator:false}},token,'PATCH');break;
                    }catch(error){
                        if(error.message!=='LAB_HTTP_409'||attempt===19)throw error;
                        await new Promise(resolve=>setTimeout(resolve,200));
                    }
                }
            }
        }
    }
    catch (error) {
        this.bridge = null;
        throw error;
    } }
    async pair(displayName) { if (!this.selfTest?.passed)
        throw Error('SELF_TEST_REQUIRED'); if (!this.userToken)
        throw Error('SIGN_IN_REQUIRED'); if (!this.vault.available())
        throw Error('SECURE_STORAGE_REQUIRED'); if (this.device)
        throw Error('ALREADY_PAIRED'); const code = await this.api('/api/v1/devices/pairing-codes', {}); const workerId = 'desktop-' + crypto.randomUUID().replaceAll('-', '').slice(0, 12); const device = await this.api('/api/v1/device/enroll', { code: code.code, workerId, displayName: displayName.trim() || 'GPU Worker', computeUrl: 'http://127.0.0.1:8765', selfTest: { ...this.selfTest, coordinator: false } }, ''); await this.vault.write('device-token', device.deviceToken); const { deviceToken, ...publicDevice } = device; this.device = publicDevice; this.settings = { ...this.settings, device: publicDevice, selfTest: this.selfTest }; await this.save(); await this.startAgent(); return publicDevice; }
    async contribution(enabled) { if (!this.bridge)
        throw Error('AGENT_UNAVAILABLE'); if (!enabled)
        await this.bridge.call('off'); if (!this.userToken) {
        if (!enabled)
            return this.bridge.call('status');
        throw Error('SIGN_IN_REQUIRED');
    } const state = await this.bridge.call('status'); return this.api('/api/v1/devices/' + this.device.deviceId + '/contribution', { enabled, bootId: state.bootId }); }
    async status() {
        if (this.autoStart && this.device && this.setup.status().installed && !this.bridge)
            try {
                await this.startAgent();
            }
            catch {
                this.lastState = { drained: false, enabled: false, error: 'AGENT_UNAVAILABLE' };
            }
        if (this.bridge)
            try {
                this.lastState = await this.bridge.call('status');
            }
            catch {
                this.lastState = { drained: false, enabled: false, error: 'AGENT_UNAVAILABLE' };
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
        return { serverUrl: this.settings.serverUrl ?? '', signedIn: !!this.userToken, session: this.session, device: this.device, selfTest: this.selfTest, setup: this.setup.status(), telemetry: p?.telemetry ?? null, telemetryHistory:p?.telemetryHistory??[], connection: p?.connection?.status ?? this.connection, agent: p ? { bootId: p.bootId, enabled: !!p.enabled, drained: p.drained, error: p.error, assignments: (p.processes ?? []).map(r => ({ assignmentId: r.assignmentId, epoch:r.epoch, workerAlive: r.workerAlive, coordinatorAlive: r.coordinatorAlive, ready: r.ready })) } : null };
    }
    async quit() { this.autoStart = false; if (this.setup.running)
        throw Error('SETUP_IN_PROGRESS'); if (!this.bridge)
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
