/**
 * Electron contract for the first minutes of the Worker (CPU only, no GPU, no real lab, no credentials):
 * lab-address entry, error messages, connection state, sign-out / sign-in, Quit while a connection hangs, and
 * the diagnostics log. Run on Linux under a virtual display:
 *   xvfb-run -a node scripts/check-worker-onboarding.cjs <fresh evidence directory>
 * It drives the Linux build of the same Electron code the Windows installer packages; it does NOT exercise
 * Windows-only behaviour (tray, NSIS, safeStorage).
 */
const { _electron: electron } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const net = require('node:net');

const output = process.argv[2];
if (!output) throw Error('Explicit fresh evidence directory required');
const freePort = () => new Promise(resolve => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const { port } = s.address(); s.close(() => resolve(port)); }); });
const listen = server => new Promise(resolve => server.listen(0, '127.0.0.1', () => resolve(server.address().port)));

(async () => {
    await fs.mkdir(output, { recursive: true });
    const receipt = path.join(output, 'worker-onboarding.json');
    try { await fs.access(receipt); throw Error('Evidence already exists'); } catch (e) { if (e.code !== 'ENOENT') throw e; }
    const root = await fs.mkdtemp(path.join(os.tmpdir(), 'worker-onboarding-'));
    const seen = { lab: [], hang: 0 };
    const lab = http.createServer((req, res) => {
        seen.lab.push(`${req.method} ${req.url} ua=${req.headers['user-agent']}`);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(req.url === '/api/v1/auth/login' ? { accessToken: 'fixture-session', user: { displayName: 'Fixture friend' } }
            : req.url === '/api/v1/auth/logout' ? {} : req.url === '/api/v1/devices' ? [] : { ok: true, agentMode: true, serverInstanceId: 'fixture-lab', deviceConfiguration: true }));
    });
    const hang = http.createServer(() => { seen.hang++; });
    const labPort = await listen(lab), hangPort = await listen(hang), deadPort = await freePort();
    const results = {};
    let app;
    const launch = async () => {
        app = await electron.launch({ args: [path.resolve('desktop/worker'), '--disable-gpu'], env: { ...process.env, CUDA_VISIBLE_DEVICES: '', HETEROES_WORKER_TEST_DATA: root }, timeout: 30000 });
        const page = await app.firstWindow();
        page.on('pageerror', error => { throw error; });
        await page.locator('.preference-menu summary').click();
        await page.locator('select[aria-label]').first().selectOption('en');
        await page.locator('.preference-menu summary').click();
        return page;
    };
    const address = page => page.getByLabel('Lab server address');
    const alert = page => page.locator('.product-alert');
    const connect = async (page, text) => { await address(page).fill(text); await page.getByRole('button', { name: 'Connect', exact: true }).click(); };
    const status = page => page.evaluate(() => window.worker.call('status'));
    try {
        let page = await launch();
        await address(page).waitFor();
        assert.equal(await address(page).inputValue(), 'https://lab.heteroes.site', 'the lab address shipped with the app is offered');
        assert.equal(await page.getByText('Network and compute role').isVisible(), false, 'network/role are tucked away while onboarding');
        results.defaultOffered = true;

        await connect(page, 'not a lab !!');
        await alert(page).getByText('not a valid lab address', { exact: false }).waitFor();
        await connect(page, '   ');
        await alert(page).getByText('INVALID_LAB_ADDRESS').waitFor();
        results.invalidAddressExplained = true;

        await connect(page, `127.0.0.1:${deadPort}`);
        await alert(page).getByText('LAB_UNREACHABLE').waitFor();
        assert.match(await alert(page).innerText(), /did not answer/);
        assert.equal((await status(page)).result.connection, 'OFFLINE');
        results.unreachableExplained = true;

        await connect(page, `127.0.0.1:${labPort}/#downloads`);
        await page.getByRole('heading', { name: 'Sign in', exact: true }).waitFor();
        const afterConnect = (await status(page)).result;
        assert.equal(afterConnect.serverUrl, `http://127.0.0.1:${labPort}`);
        assert.equal(afterConnect.connection, 'ONLINE');
        assert.equal(await alert(page).count(), 0, 'a successful connection clears the error');
        results.connectedOnline = true;
        results.pastedUrlReducedToOrigin = true;

        await page.getByRole('button', { name: 'Change lab' }).click();
        assert.equal(await address(page).inputValue(), `http://127.0.0.1:${labPort}`);
        await page.getByRole('button', { name: 'Cancel' }).click();
        await page.getByLabel('Username').waitFor();
        results.changeLabAndCancel = true;

        await page.getByLabel('Username').fill('friend');
        await page.getByLabel('Password').fill('hunter2-never-logged');
        await page.getByRole('button', { name: 'Sign in', exact: true }).click();
        await page.getByRole('button', { name: 'Sign out' }).waitFor();
        await page.getByRole('button', { name: 'Sign out' }).click();
        await page.getByLabel('Username').waitFor();
        assert.equal((await status(page)).result.signedIn, false);
        await page.getByLabel('Username').fill('friend');
        await page.getByLabel('Password').fill('hunter2-never-logged');
        await page.getByRole('button', { name: 'Sign in', exact: true }).click();
        await page.getByRole('button', { name: 'Sign out' }).waitFor();
        results.signOutAndBackIn = true;

        // Quit while a connection attempt is hanging: the button stays usable and the app really exits.
        await page.getByRole('button', { name: 'Sign out' }).click();
        await page.getByLabel('Username').waitFor();
        await page.getByRole('button', { name: 'Change lab' }).click();
        await address(page).fill(`127.0.0.1:${hangPort}`);
        await page.getByRole('button', { name: 'Connect', exact: true }).click();
        for (let i = 0; i < 50 && !seen.hang; i++) await new Promise(r => setTimeout(r, 100));
        assert.ok(seen.hang, 'the fixture lab received the hanging request');
        const quitButton = page.getByRole('button', { name: 'Quit safely' });
        assert.equal(await quitButton.isEnabled(), true, 'Quit is available while a connection is pending');
        const closed = app.waitForEvent('close');
        const started = Date.now();
        await quitButton.click().catch(() => { });
        await Promise.race([closed, new Promise((_, reject) => setTimeout(() => reject(Error('app did not exit within 10 s while a connection was pending')), 10000))]);
        results.quitWhileConnectingMs = Date.now() - started;
        app = null;

        page = await launch();
        const closedAgain = app.waitForEvent('close');
        await page.getByRole('button', { name: 'Quit safely' }).click().catch(() => { });
        await Promise.race([closedAgain, new Promise((_, reject) => setTimeout(() => reject(Error('plain Quit did not exit')), 10000))]);
        app = null;
        results.plainQuitExits = true;

        const log = await fs.readFile(path.join(root, 'logs', 'worker.log'), 'utf8');
        assert.match(log, / action action=connect ok=false code=LAB_UNREACHABLE/);
        assert.match(log, / action action=login ok=true/);
        assert.ok(!/hunter2|fixture-session/.test(log), 'the log never holds the password or session');
        results.logHasActionsNoSecrets = true;
        assert.ok(seen.lab.every(line => line.includes('ua=HeteroES-Worker/')), 'every request identifies itself');
        results.requestsIdentifyThemselves = true;

        await fs.writeFile(receipt, JSON.stringify({ gpuWork: false, realLab: false, platformExercised: process.platform, windowsExercised: false, ...results, labRequests: seen.lab.length }, null, 2) + '\n', { flag: 'wx' });
        console.log('PASS Worker onboarding contract on', process.platform, '(not a Windows run).');
    } finally {
        if (app) await app.close().catch(() => { });
        await Promise.all([lab, hang].map(s => new Promise(resolve => { s.closeAllConnections?.(); s.close(resolve); })));
        await fs.rm(root, { recursive: true, force: true });
    }
})().catch(error => { console.error(error.stack || error.message); process.exitCode = 1; });
