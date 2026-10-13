/**
 * Electron contract for the paired Worker ("GPU station"): CPU only, synthetic pairing, no GPU, no real lab.
 *   xvfb-run -a node scripts/check-worker-station.cjs <fresh evidence directory>
 * It does NOT start the agent or a runtime, so "working" and the gauges with real values are covered by unit tests
 * (desktop/worker/tests/station.test.mjs), not by this run.
 */
const { _electron: electron } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');

const output = process.argv[2];
if (!output) throw Error('Explicit fresh evidence directory required');
(async () => {
    await fs.mkdir(output, { recursive: true });
    const receipt = path.join(output, 'worker-station.json');
    try { await fs.access(receipt); throw Error('Evidence already exists'); } catch (e) { if (e.code !== 'ENOENT') throw e; }
    const root = await fs.mkdtemp(path.join(os.tmpdir(), 'worker-station-'));
    const server = http.createServer((req, res) => {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(req.url === '/api/v1/auth/login' ? { accessToken: 'fixture', user: { displayName: 'Fixture' } } : req.url === '/api/v1/devices' ? [{ deviceId: 'synthetic', approvalStatus: 'APPROVED' }] : { ok: true, agentMode: true, serverInstanceId: 'fixture', deviceConfiguration: true }));
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    await fs.writeFile(path.join(root, 'settings.json'), JSON.stringify({
        serverUrl: `http://127.0.0.1:${server.address().port}`, serverInstanceId: 'fixture',
        selfTest: { passed: true, coordinator: false, platform: 'windows', gpuName: 'NVIDIA GeForce RTX 3060', vramTotalMb: 12288 },
        device: { deviceId: 'synthetic', workerId: 'desktop-synthetic', displayName: 'My gaming PC', approvalStatus: 'APPROVED' },
    }));
    const results = {};
    let app;
    try {
        app = await electron.launch({ args: [path.resolve('desktop/worker'), '--disable-gpu'], env: { ...process.env, CUDA_VISIBLE_DEVICES: '', HETEROES_WORKER_TEST_DATA: root }, timeout: 30000 });
        const page = await app.firstWindow();
        page.on('pageerror', error => { throw error; });
        await page.locator('.preference-menu summary').click();
        await page.locator('select[aria-label]').first().selectOption('en');
        await page.locator('.preference-menu summary').click();

        const station = page.locator('.station');
        await station.waitFor();
        await station.getByText('NVIDIA GeForce RTX 3060').waitFor();
        await station.getByText('12.0 GiB VRAM').waitFor();
        await station.getByText('My gaming PC').waitFor();
        results.stationShowsTheGpu = true;
        const toggle = page.getByRole('switch');
        assert.equal(await toggle.isDisabled(), true, 'signed out: the switch cannot be pressed');
        await station.getByText('Sign in to start contributing.').waitFor();
        results.signedOutExplained = true;
        assert.equal(await page.locator('.gauge').count(), 3);
        assert.equal(await page.locator('.gauge-bar[aria-valuenow]').count(), 0, 'no agent: no measurement is invented');
        results.gaugesStayUnknown = true;
        assert.equal(await page.getByText('Network and compute role').isVisible(), false, 'advanced settings are folded away');
        const size = await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].getSize());
        assert.ok(size[0] <= 900, `a compact window, not a wide dashboard (${size[0]} px)`);
        results.compactWindow = size;
        await page.screenshot({ path: path.join(output, 'station-signed-out.png') });

        await page.getByLabel('Username').fill('fixture');
        await page.getByLabel('Password').fill('synthetic-password');
        await page.getByRole('button', { name: 'Sign in', exact: true }).click();
        await station.getByText('The local agent is not running yet.').waitFor();
        results.nextBlockerExplained = true;

        await page.getByText('Advanced: network, role, assignments and diagnostics').click();
        await page.getByText('Network and compute role').waitFor();
        await page.getByRole('heading', { name: 'Device overview' }).waitFor();
        results.advancedOpensOnDemand = true;
        await page.screenshot({ path: path.join(output, 'station-advanced.png'), fullPage: true });

        for (const width of [360, 600, 900]) {
            await page.setViewportSize({ width, height: 800 });
            assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `overflow at ${width}`);
        }
        results.noOverflow = true;
        const closed = app.waitForEvent('close');
        await page.getByRole('button', { name: 'Quit safely' }).click().catch(() => { });
        await Promise.race([closed, new Promise((_, reject) => setTimeout(() => reject(Error('Quit did not exit')), 10000))]);
        app = null;
        await fs.writeFile(receipt, JSON.stringify({ gpuWork: false, realLab: false, agentStarted: false, platformExercised: process.platform, windowsExercised: false, ...results }, null, 2) + '\n', { flag: 'wx' });
        console.log('PASS Worker station contract (CPU fixture; not a Windows run).');
    } finally {
        if (app) await app.close().catch(() => { });
        await new Promise(resolve => { server.closeAllConnections?.(); server.close(resolve); });
        await fs.rm(root, { recursive: true, force: true });
    }
})().catch(error => { console.error(error.stack || error.message); process.exitCode = 1; });
