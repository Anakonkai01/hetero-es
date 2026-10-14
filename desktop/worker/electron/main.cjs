const { app, BrowserWindow, ipcMain, safeStorage, Tray, Menu, shell, dialog, nativeImage, Notification } = require('electron');
const path = require('node:path');
const fs = require('node:fs/promises');
const { Service } = require('./service.cjs');
const { Vault } = require('./vault.cjs');
const { Lifecycle, codeOf } = require('./lifecycle.cjs');
const { createLog } = require('./log.cjs');
if (!app.isPackaged && process.env.HETEROES_WORKER_TEST_DATA)
    app.setPath('userData', process.env.HETEROES_WORKER_TEST_DATA);
const log = createLog(path.join(app.getPath('userData'), 'logs'));
process.on('uncaughtException', error => log.error('uncaught exception', error));
process.on('unhandledRejection', error => log.error('unhandled rejection', error instanceof Error ? error : Error('ACTION_FAILED')));
const ownsInstance = app.requestSingleInstanceLock();
if (!ownsInstance)
    app.quit();
let window, tray, service, lifecycle, hintedTray = false;
const external = { tailscale: 'https://tailscale.com/download', help: 'https://tailscale.com/kb/1017/install', windowsRuntime: 'https://aka.ms/vs/17/release/vc_redist.x64.exe' };
function show() { if (!window)
    return; window.show(); window.focus(); }
// A visible message box: a toast can be silenced by the system, and silence is how earlier builds hid problems.
function notify(title, body) { void dialog.showMessageBox({ type: 'info', title, message: body, buttons: ['OK'] }); }
const fail = (title, body) => dialog.showErrorBox(title, body);
app.on('second-instance', show);
app.on('before-quit', event => { if (lifecycle && !lifecycle.exiting) {
    event.preventDefault();
    void lifecycle.userQuit();
} });
app.on('window-all-closed', () => { });
app.whenReady().then(async () => {
    if (!ownsInstance)
        return;
    const root = app.getPath('userData'), resources = app.isPackaged ? path.join(process.resourcesPath, 'worker') : path.join(__dirname, '../resources');
    log.info('starting', { version: app.getVersion(), platform: process.platform, packaged: app.isPackaged });
    service = new Service(root, resources, new Vault(root, safeStorage), { log });
    // Which lab this app talks to (host only) and whether a device is paired: the first thing support asks.
    log.info('lab', { host: (() => { try { return new URL(service.settings.serverUrl).hostname; } catch { return ''; } })(), paired: !!service.device, build: service.defaults.build });
    lifecycle = new Lifecycle({ service, quitApp: () => app.quit(), show, notify, fail, log });
    window = new BrowserWindow({ width: 820, height: 780, minWidth: 360, minHeight: 520, show: false, backgroundColor: '#101a23', webPreferences: { preload: path.join(__dirname, 'preload.cjs'), sandbox: true, contextIsolation: true, nodeIntegration: false } });
    window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    window.webContents.on('will-navigate', event => event.preventDefault());
    window.webContents.session.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
    window.on('close', event => { if (!lifecycle.exiting) {
        event.preventDefault();
        window.hide();
        if (!hintedTray && Notification.isSupported()) {
            hintedTray = true;
            new Notification({ title: 'HeteroES Worker', body: 'Still running in the tray. Use Quit safely to exit. / Vẫn chạy ở khay hệ thống. Chọn Thoát an toàn để thoát.' }).show();
        }
    } });
    tray = new Tray(nativeImage.createFromPath(path.join(resources, 'tray.png')));
    tray.setToolTip('HeteroES Worker');
    tray.on('click', show);
    tray.setContextMenu(Menu.buildFromTemplate([{ label: 'Open HeteroES Worker / Mở ứng dụng', click: show }, { label: 'Stop safely / Dừng an toàn', click: () => void lifecycle.stopSafely() }, { label: 'Quit safely / Thoát an toàn', click: () => void lifecycle.userQuit() }]));
    async function execute(action, args) {
        if (action === 'connect') {
            if (typeof args.url !== 'string' || args.url.length > 2048)
                throw Error('INVALID_LAB_ADDRESS');
            return service.connect(args.url);
        }
        if (action === 'login') {
            if (typeof args.username !== 'string' || typeof args.password !== 'string' || args.username.length > 200 || args.password.length > 1000)
                throw Error('INVALID_ARGUMENT');
            return service.login(args.username, args.password);
        }
        if (action === 'configureCompute')
            return service.configureCompute(args);
        if (action === 'checkConnection')
            return service.checkConnection();
        if (action === 'install')
            return service.setup.install();
        if (action === 'selftest')
            return service.selftest();
        if (action === 'pair') {
            if (typeof args.displayName !== 'string' || args.displayName.trim().length > 100)
                throw Error('INVALID_ARGUMENT');
            return service.pair(args.displayName);
        }
        if (action === 'contribution') {
            if (typeof args.enabled !== 'boolean')
                throw Error('INVALID_ARGUMENT');
            return service.contribution(args.enabled);
        }
        if (action === 'logout')
            return service.logout();
        if (action === 'forgetDevice')
            return service.forgetDevice();
        if (action === 'external') {
            const url = args.target === 'lab' ? (service.settings.uiUrl ?? service.settings.serverUrl) : external[args.target];
            if (!url)
                throw Error('INVALID_EXTERNAL_TARGET');
            await shell.openExternal(url);
            return { opened: true };
        }
        if (action === 'diagnostics') {
            const state = await service.status();
            const report = { version: app.getVersion(), build: state.build, platform: process.platform, setup: state.setup, connection: state.connection, selfTest: state.selfTest, agent: state.agent, lab: (() => { try { return new URL(state.serverUrl).hostname; } catch { return ''; } })(), log: log.tail(200).split('\n') };
            const destination = await dialog.showSaveDialog(window, { defaultPath: 'heteroes-diagnostics.json', filters: [{ name: 'JSON', extensions: ['json'] }] });
            if (!destination.canceled) {
                await fs.writeFile(destination.filePath, JSON.stringify(report, null, 2), { mode: 0o600 });
            }
            return { exported: !destination.canceled };
        }
        throw Error('INVALID_COMMAND');
    }
    ipcMain.handle('worker:command', async (event, action, args) => {
        if (event.sender !== window.webContents || event.senderFrame !== window.webContents.mainFrame)
            return { ok: false, error: 'IPC_DENIED' };
        const actions = ['status', 'connect', 'checkConnection', 'configureCompute', 'login', 'install', 'selftest', 'pair', 'contribution', 'logout', 'forgetDevice', 'quit', 'external', 'diagnostics'];
        if (!actions.includes(action) || !args || typeof args !== 'object' || Array.isArray(args))
            return { ok: false, error: 'INVALID_COMMAND' };
        const allowed = { connect: ['url'], configureCompute: ['network', 'coordinator', 'host'], login: ['username', 'password'], pair: ['displayName'], contribution: ['enabled'], external: ['target'] };
        if (Object.keys(args).some(key => !(allowed[action] ?? []).includes(key)))
            return { ok: false, error: 'INVALID_ARGUMENT' };
        const started = Date.now();
        try {
            const result = action === 'status' ? await service.status() : action === 'quit' ? await lifecycle.quit() : await lifecycle.run(action, () => execute(action, args));
            if (action !== 'status')
                log.info('action', { action, ok: true, ms: Date.now() - started });
            return { ok: true, result };
        }
        catch (error) {
            const code = codeOf(error);
            log.info('action', { action, ok: false, code, ms: Date.now() - started });
            return { ok: false, error: code };
        }
    });
    await window.loadFile(path.join(__dirname, '../dist/index.html'));
    show();
}).catch(error => (lifecycle ?? new Lifecycle({ service: null, quitApp: () => app.quit(), show, notify, fail, log })).startupFailed(error));
