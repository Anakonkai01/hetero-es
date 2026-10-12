const { app, BrowserWindow, ipcMain, safeStorage, Tray, Menu, shell, dialog, nativeImage } = require('electron');
const path = require('node:path');
const fs = require('node:fs/promises');
const { Service } = require('./service.cjs');
const { Vault } = require('./vault.cjs');
if (!app.isPackaged && process.env.HETEROES_WORKER_TEST_DATA)
    app.setPath('userData', process.env.HETEROES_WORKER_TEST_DATA);
const ownsInstance = app.requestSingleInstanceLock();
if (!ownsInstance)
    app.quit();
let window, tray, service, exiting = false, busy = false;
const external = { tailscale: 'https://tailscale.com/download', help: 'https://tailscale.com/kb/1017/install', windowsRuntime: 'https://aka.ms/vs/17/release/vc_redist.x64.exe' };
function show() { if (!window)
    return; window.show(); window.focus(); }
async function quit() { if (busy)
    throw Error('ACTION_IN_PROGRESS'); const state = await service.quit(); if (!state.drained) {
    show();
    return state;
} exiting = true; app.quit(); return state; }
app.on('second-instance', show);
app.on('before-quit', event => { if (!exiting) {
    event.preventDefault();
    quit().catch(() => show());
} });
app.on('window-all-closed', () => { });
app.whenReady().then(async () => {
    if (!ownsInstance)
        return;
    const root = app.getPath('userData'), resources = app.isPackaged ? path.join(process.resourcesPath, 'worker') : path.join(__dirname, '../resources');
    service = new Service(root, resources, new Vault(root, safeStorage));
    window = new BrowserWindow({ width: 1050, height: 820, minWidth: 360, minHeight: 520, show: false, backgroundColor: '#101a23', webPreferences: { preload: path.join(__dirname, 'preload.cjs'), sandbox: true, contextIsolation: true, nodeIntegration: false } });
    window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    window.webContents.on('will-navigate', event => event.preventDefault());
    window.webContents.session.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
    window.on('close', event => { if (!exiting) {
        event.preventDefault();
        window.hide();
    } });
    tray = new Tray(nativeImage.createFromPath(path.join(resources, 'tray.png')));
    tray.setToolTip('HeteroES Worker');
    tray.on('click', show);
    tray.setContextMenu(Menu.buildFromTemplate([{ label: 'Open HeteroES Worker / Mở ứng dụng', click: show }, { label: 'Stop safely / Dừng an toàn', click: () => service.contribution(false).catch(() => show()) }, { label: 'Quit safely / Thoát an toàn', click: () => quit().catch(() => show()) }]));
    ipcMain.handle('worker:command', async (event, action, args) => {
        if (event.sender !== window.webContents || event.senderFrame !== window.webContents.mainFrame)
            return { ok: false, error: 'IPC_DENIED' };
        const actions = ['status', 'connect', 'checkConnection', 'configureCompute', 'login', 'install', 'selftest', 'pair', 'contribution', 'logout', 'quit', 'external', 'diagnostics'];
        if (!actions.includes(action) || !args || typeof args !== 'object' || Array.isArray(args))
            return { ok: false, error: 'INVALID_COMMAND' };
        const allowed = { connect: ['url'], configureCompute: ['network', 'coordinator', 'host'], login: ['username', 'password'], pair: ['displayName'], contribution: ['enabled'], external: ['target'] };
        if (Object.keys(args).some(key => !(allowed[action] ?? []).includes(key)))
            return { ok: false, error: 'INVALID_ARGUMENT' };
        if (action !== 'status' && busy)
            return { ok: false, error: 'ACTION_IN_PROGRESS' };
        if (action !== 'status')
            busy = true;
        try {
            let result;
            if (action === 'status')
                result = await service.status();
            if (action === 'connect') {
                if (typeof args.url !== 'string' || args.url.length > 2048)
                    throw Error('INVALID_LAB_ADDRESS');
                result = await service.connect(args.url);
            }
            if (action === 'login') {
                if (typeof args.username !== 'string' || typeof args.password !== 'string' || args.username.length > 200 || args.password.length > 1000)
                    throw Error('INVALID_ARGUMENT');
                result = await service.login(args.username, args.password);
            }
            if (action === 'configureCompute') result = await service.configureCompute(args);
            if (action === 'checkConnection') result = await service.checkConnection();
            if (action === 'install')
                result = await service.setup.install();
            if (action === 'selftest')
                result = await service.selftest();
            if (action === 'pair') {
                if (typeof args.displayName !== 'string' || args.displayName.trim().length > 100)
                    throw Error('INVALID_ARGUMENT');
                result = await service.pair(args.displayName);
            }
            if (action === 'contribution') {
                if (typeof args.enabled !== 'boolean')
                    throw Error('INVALID_ARGUMENT');
                result = await service.contribution(args.enabled);
            }
            if (action === 'logout')
                result = await service.logout();
            if (action === 'quit') {
                busy = false;
                result = await quit();
            }
            if (action === 'external') {
                const url = args.target === 'lab' ? (service.settings.uiUrl??service.settings.serverUrl) : external[args.target];
                if (!url)
                    throw Error('INVALID_EXTERNAL_TARGET');
                await shell.openExternal(url);
                result = { opened: true };
            }
            if (action === 'diagnostics') {
                const state = await service.status();
                const report = { version: app.getVersion(), platform: process.platform, setup: state.setup, connection: state.connection, selfTest: state.selfTest, agent: state.agent };
                const destination = await dialog.showSaveDialog(window, { defaultPath: 'heteroes-diagnostics.json', filters: [{ name: 'JSON', extensions: ['json'] }] });
                if (!destination.canceled) {
                    await fs.writeFile(destination.filePath, JSON.stringify(report, null, 2), { mode: 0o600 });
                }
                result = { exported: !destination.canceled };
            }
            return { ok: true, result };
        }
        catch (error) {
            const code = /^[A-Z][A-Z0-9_]+$/.test(error.message) ? error.message : 'ACTION_FAILED';
            return { ok: false, error: code };
        }
        finally {
            if (action !== 'status')
                busy = false;
        }
    });
    await window.loadFile(path.join(__dirname, '../dist/index.html'));
    show();
}).catch(() => { exiting = true; app.quit(); });
