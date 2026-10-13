/**
 * Watches ONE run while it happens, from the outside, the way a browser does. Read-only: it never creates or changes anything.
 *   node scripts/record-live-run.mjs <base url> <fresh output directory> [--after <epoch seconds>] [--minutes 20] [--credentials <file>]
 * It waits for an experiment created after --after (default: now) and then
 *   - opens its event stream (Authorization header, like the web app) and records every message with its arrival time
 *     (timeline snapshots, heartbeats, the final "end"), which shows whether the tunnel buffers or cuts the stream, and
 *   - signs in with a browser and screenshots the "Live and replay" tab every 20 s, recording whether the diagram was drawn
 *     and any console error.
 * The password comes from the credentials file and is never printed or written.
 */
import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

const [base, output] = process.argv.slice(2);
if (!base || !output) throw Error('usage: record-live-run.mjs <base url> <fresh output directory> [options]');
const option = (name, fallback) => { const i = process.argv.indexOf(name); return i > 0 ? process.argv[i + 1] : fallback; };
const after = Number(option('--after', String(Date.now() / 1000)));
const minutes = Number(option('--minutes', '20'));
const credentialsFile = option('--credentials', path.join(os.homedir(), '.config/heteroes-m2/credentials.json'));
const password = JSON.parse(await fs.readFile(credentialsFile, 'utf8')).users?.admin;
if (!password) throw Error('No admin password in the credentials file');
await fs.mkdir(output, { recursive: true });
const resultFile = path.join(output, 'live-run.json');
try { await fs.access(resultFile); throw Error('Evidence already exists'); } catch (error) { if (error.code !== 'ENOENT') throw error; }

const started = Date.now();
const seconds = () => Math.round((Date.now() - started) / 100) / 10;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const TERMINAL = new Set(['COMPLETED', 'CANCELLED', 'FAILED']);

const session = await (await fetch(base + '/api/v1/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: 'admin', password }) })).json();
const auth = { Authorization: 'Bearer ' + session.accessToken, 'X-Workspace-Id': session.workspaces[0].workspaceId };
const api = async route => (await fetch(base + '/api/v1' + route, { headers: auth })).json();

let run;
for (let i = 0; i < minutes * 30 && !run; i++) {
    run = (await api('/experiments')).find(e => Date.parse(e.createdAt) / 1000 >= after);
    if (!run) await sleep(2000);
}
if (!run) throw Error('no new experiment appeared');
console.log(`${seconds()}s watching ${run.experimentId} (${run.status})`);

const messages = [];
const streaming = (async () => {
    const reply = await fetch(`${base}/api/v1/experiments/${run.experimentId}/stream`, { headers: { ...auth, Accept: 'text/event-stream' } });
    const contentType = reply.headers.get('content-type');
    const decoder = new TextDecoder();
    let buffer = '';
    for await (const chunk of reply.body) {
        buffer += decoder.decode(chunk, { stream: true });
        let cut;
        while ((cut = buffer.indexOf('\n\n')) >= 0) {
            const block = buffer.slice(0, cut); buffer = buffer.slice(cut + 2);
            if (block.startsWith(':')) { messages.push({ at: seconds(), kind: 'heartbeat' }); continue; }
            const kind = /^event: (.*)$/m.exec(block)?.[1];
            const data = /^data: (.*)$/m.exec(block)?.[1];
            const timeline = kind === 'timeline' && data ? JSON.parse(data) : null;
            messages.push({
                at: seconds(), kind, bytes: data?.length ?? 0,
                ...(timeline ? { nowMs: timeline.nowMs, status: timeline.experiment.status, jobs: timeline.jobs.length, jobsEnded: timeline.jobs.filter(j => j.endMs !== null).length, generations: timeline.generations.length, marks: timeline.marks.length } : {}),
            });
            console.log(`${seconds()}s ${kind ?? 'message'}`);
        }
    }
    return contentType;
})();

const browser = await chromium.launch({ headless: true });
const shots = [];
const problems = [];
try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'vi-VN' });
    const page = await context.newPage();
    page.on('pageerror', error => problems.push('pageerror: ' + error.message));
    page.on('console', message => { if (message.type() === 'error' && !/status of 401/.test(message.text())) problems.push('console: ' + message.text().slice(0, 200)); });
    await page.goto(base + '/login');
    await page.locator('input[autocomplete="username"]').fill('admin');
    await page.locator('input[autocomplete="current-password"]').fill(password);
    await page.locator('form button[type="submit"]').click();
    await page.waitForURL(url => !url.pathname.startsWith('/login'), { timeout: 30000 });
    await page.goto(`${base}/experiments/${run.experimentId}?tab=live`);
    let ended = false;
    streaming.then(() => { ended = true; }, () => { ended = true; });
    for (let n = 0; n < minutes * 3 && !ended; n++) {
        await page.waitForTimeout(n === 0 ? 4000 : 20000);
        const drawn = await page.evaluate(() => ({ diagram: Boolean(document.querySelector('.lv-diagram')), gpuCards: document.querySelectorAll('.lv-card').length, packets: document.querySelectorAll('.lv-packet').length }));
        const name = `live-${String(n).padStart(2, '0')}.png`;
        await page.screenshot({ path: path.join(output, name), fullPage: false });
        shots.push({ name, at: seconds(), ...drawn });
    }
    await page.waitForTimeout(3000);
    await page.screenshot({ path: path.join(output, 'live-final.png'), fullPage: true });
    shots.push({ name: 'live-final.png', at: seconds() });
} finally { await browser.close(); }

const contentType = await streaming.catch(error => 'error: ' + error.message);
const final = await api(`/experiments/${run.experimentId}`);
const timelines = messages.filter(m => m.kind === 'timeline');
await fs.writeFile(resultFile, JSON.stringify({
    base, experimentId: run.experimentId, finalStatus: final.status, completedGenerations: final.completedGenerations, totalSeconds: seconds(),
    stream: { contentType, messages: messages.length, timelines: timelines.length, heartbeats: messages.filter(m => m.kind === 'heartbeat').length, ended: messages.some(m => m.kind === 'end'),
        longestSilence: Math.max(0, ...messages.slice(1).map((m, i) => Math.round((m.at - messages[i].at) * 10) / 10)), messages },
    screenshots: shots, browserProblems: problems,
}, null, 1) + '\n');
console.log(JSON.stringify({ status: final.status, timelines: timelines.length, ended: messages.some(m => m.kind === 'end'), problems: problems.length }));
