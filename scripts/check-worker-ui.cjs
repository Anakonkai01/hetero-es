/** Electron UI contract with synthetic qualification and a CPU-only lab fixture. */
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
    const receipt = path.join(output, 'worker-ui.json');
    try { await fs.access(receipt); throw Error('Evidence already exists'); } catch (e) { if (e.code !== 'ENOENT') throw e; }
    const root = await fs.mkdtemp(path.join(os.tmpdir(), 'worker-ui-'));
    const requests = [];
    const server = http.createServer((req, res) => {
        requests.push(req.url);
        assert.ok(req.method === 'GET' || (req.method === 'POST' && req.url === '/api/v1/auth/login'));
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(req.url === '/api/v1/auth/login' ? { accessToken: 'synthetic-ui-session', user: { displayName: 'CPU fixture' } } :
            req.url === '/api/v1/devices' ? [] : { ok: true, agentMode: true, serverInstanceId: 'cpu-fixture', deviceConfiguration: true }));
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    let app;
    const launch = async (platform, extra = {}) => {
        await fs.writeFile(path.join(root, 'settings.json'), JSON.stringify({
            serverUrl: `http://127.0.0.1:${server.address().port}`, serverInstanceId: 'cpu-fixture',
            selfTest: { passed: true, coordinator: true, platform, vramTotalMb: 16000 },
            ...extra,
        }));
        app = await electron.launch({ args: [path.resolve('desktop/worker'), '--disable-gpu'],
            env: { ...process.env, CUDA_VISIBLE_DEVICES: '', HETEROES_WORKER_TEST_DATA: root }, timeout: 30000 });
        const page = await app.firstWindow();
        await page.locator('.preference-menu summary').click();
        await page.locator('select[aria-label]').first().selectOption('en');
        await page.locator('.preference-menu summary').click();
        return page;
    };
    try {
        let page = await launch('linux');
        const role = page.getByLabel('Allow this computer to coordinate experiments');
        await role.waitFor();
        assert.equal(await role.isChecked(), false);
        await role.check();
        const addresses = await page.getByLabel('Coordinator private address').locator('option').allTextContents();
        assert.ok(addresses.length);
        await role.uncheck();
        await page.getByLabel('Network', { exact: true }).selectOption('internet');
        await page.getByRole('button', { name: 'Save network and role' }).click();
        await page.waitForFunction(() => !document.querySelector('button:disabled'));
        const stored = JSON.parse(await fs.readFile(path.join(root, 'settings.json'), 'utf8'));
        assert.deepEqual(stored.compute, { network: 'internet', coordinator: false, host: '127.0.0.1' });
        await page.getByRole('button', { name: 'Check connection', exact: true }).last().click();
        await page.getByText('Lab server is reachable.', { exact: false }).waitFor();
        assert.equal(await page.getByText('Not tested yet: no current worker assignment.', { exact: false }).count(), 2);
        const sizes = [];
        for (const width of [1280, 780, 360]) {
            await page.setViewportSize({ width, height: 900 });
            const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
            assert.equal(overflow, false, `Horizontal overflow at ${width}px`);
            await page.screenshot({ path: path.join(output, `worker-${width}.png`), fullPage: true });
            sizes.push(width);
        }
        await app.close(); app = null;
        page = await launch('windows');
        await page.getByText('Coordinator requires a qualified Linux GPU with at least 11000 MB VRAM.').waitFor();
        assert.equal(await page.getByLabel('Allow this computer to coordinate experiments').count(), 0);
        const invalid = await page.evaluate(() => window.worker.call('configureCompute', { network: 'lan', coordinator: true, host: '127.0.0.1' }));
        assert.equal(invalid.error, 'COORDINATOR_NOT_QUALIFIED');
        await app.close(); app = null;
        page = await launch('linux', { computePending: { network: 'lan', coordinator: true, host: '192.168.1.8' },
            device: { deviceId: 'synthetic', workerId: 'synthetic', displayName: 'CPU fixture', approvalStatus: 'APPROVED' } });
        await page.getByText('The last server reply was lost.', { exact: false }).waitFor();
        assert.equal(await page.getByRole('button', { name: 'Save network and role' }).isDisabled(), true);
        await page.getByLabel('Username', { exact: true }).fill('cpu-fixture');
        await page.getByLabel('Password', { exact: true }).fill('synthetic-password');
        await page.getByRole('button', { name: 'Sign in', exact: true }).click();
        await page.waitForFunction(() => Array.from(document.querySelectorAll('button')).some(b => b.textContent === 'Save network and role' && !b.disabled));
        await fs.writeFile(receipt, JSON.stringify({ gpuWork: false, syntheticQualification: true, realElectron: true,
            roleVisibility: true, savedNetwork: true, unassignedComputeExplicitlyUntested: true,
            windowsCoordinatorRejected: true, pendingRoleCanBeConfirmedAfterLogin: true, widths: sizes, requests,
            ordinaryOwnerDesktopWalkthrough: false }, null, 2) + '\n', { flag: 'wx' });
        console.log('PASS Worker UI; CPU fixture, no GPU work.');
    } finally {
        if (app) await app.close();
        await new Promise(resolve => server.close(resolve));
        await fs.rm(root, { recursive: true, force: true });
    }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
