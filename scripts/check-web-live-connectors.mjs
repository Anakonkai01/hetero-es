/** Connector and device-label regression check against a disposable loopback fixture lab. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';

const [base, output] = process.argv.slice(2);
if (!base || !output || new URL(base).hostname !== '127.0.0.1') throw Error('Use a disposable loopback fixture lab');
await fs.mkdir(output, { recursive: false });
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, locale: 'en-US' });
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto(base + '/login');
  await page.locator('input[autocomplete="username"]').fill('admin');
  await page.locator('input[autocomplete="current-password"]').fill('test-admin-pass');
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL((url) => !url.pathname.startsWith('/login'));
  await page.goto(base + '/experiments');
  await page.locator('a', { hasText: 'M2 three GPU agent acceptance v2' }).first().click();
  const runId = new URL(page.url()).pathname.split('/').at(-1);
  const timeline = await page.evaluate(async (id) => {
    const response = await fetch(`/api/v1/experiments/${id}/timeline`, {
      headers: {
        Authorization: 'Bearer ' + sessionStorage.getItem('heteroes.access-token'),
        'X-Workspace-Id': 'lab',
      },
    });
    if (!response.ok) throw Error('Fixture timeline unavailable');
    return response.json();
  }, runId);
  const ids = ['cli-71b757062fd9', 'cli-34312a79fbbc', 'desktop-d9017660e75f'];
  const names = ['nhan', 'nhut', 'quang'];
  const gpus = ['NVIDIA GeForce RTX 5070 Ti', 'NVIDIA GeForce RTX 5070 Ti', 'NVIDIA GeForce RTX 3060'];
  const remap = new Map(timeline.workers.map((worker, index) => [worker.id, ids[index]]));
  timeline.workers = timeline.workers.map((worker, index) => ({
    ...worker,
    id: ids[index],
    name: names[index],
    gpuName: gpus[index],
  }));
  for (const item of [...timeline.jobs, ...timeline.marks])
    if (remap.has(item.workerId)) item.workerId = remap.get(item.workerId);
  await page.route('**/api/v1/experiments/*/stream', (route) =>
    route.fulfill({
      contentType: 'text/event-stream',
      body: `event: timeline\ndata: ${JSON.stringify(timeline)}\n\nevent: end\ndata: {}\n\n`,
    }),
  );
  await page.getByRole('tab', { name: 'Live and replay' }).click();
  await page.locator('.lv-diagram').waitFor();
  await page.locator('.lv-scrub').evaluate((el) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, '450');
    el.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await page.waitForTimeout(100);
  await page.locator('.lv-stage').screenshot({ path: path.join(output, 'three-gpus.png') });
  await page.locator('.lv-table').screenshot({ path: path.join(output, 'gpu-table.png') });
  assert.equal(
    await page
      .locator('.lv-state')
      .filter({ hasText: /^RTX 5070 Ti$/ })
      .count(),
    2,
  );
  assert.equal(
    await page
      .locator('.lv-state')
      .filter({ hasText: /^RTX 3060$/ })
      .count(),
    1,
  );
  for (let index = 0; index < names.length; index++) {
    const label = page.locator('.lv-table tbody th').nth(index);
    assert.ok((await label.innerText()).includes(names[index]), 'GPU row must show the device name');
    assert.ok((await label.innerText()).includes(gpus[index]), 'GPU row must identify its GPU model');
    assert.ok(!(await label.innerText()).includes(ids[index]), 'internal identifiers belong in the tooltip');
    assert.equal(await label.getAttribute('title'), ids[index]);
  }
  const geometry = await page.locator('.lv-diagram').evaluate((svg) => {
    const coordinator = svg.querySelector('.lv-coordinator rect');
    const sourceX = +coordinator.getAttribute('x') + +coordinator.getAttribute('width') / 2;
    const sourceY = +coordinator.getAttribute('y') + +coordinator.getAttribute('height');
    return [...svg.querySelectorAll('.lv-link')].map((link, index) => {
      const card = svg.querySelectorAll('.lv-card > rect')[index];
      const targetX = +card.getAttribute('x') + +card.getAttribute('width') / 2;
      const targetY = +card.getAttribute('y');
      const total = link.getTotalLength();
      return Array.from({ length: 51 }, (_, step) => {
        const p = link.getPointAtLength((total * step) / 50);
        return (
          p.x >= Math.min(sourceX, targetX) - 0.1 &&
          p.x <= Math.max(sourceX, targetX) + 0.1 &&
          p.y >= sourceY - 0.1 &&
          p.y <= targetY + 0.1
        );
      }).every(Boolean);
    });
  });
  assert.deepEqual(geometry, [true, true, true], 'visible SVG cables must directly connect the first row');
  for (const width of [375, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
    await page.screenshot({ path: path.join(output, `replay-${width}.png`), fullPage: true });
  }
  for (let index = 3; index < 8; index++)
    timeline.workers.push({
      id: `fixture-${index}`,
      name: `GPU host ${index + 1}`,
      gpuName: 'RTX 3060',
      started: true,
      alive: true,
    });
  await page.reload();
  await page.getByRole('tab', { name: 'Live and replay' }).click();
  await page.locator('.lv-card').nth(7).waitFor();
  await page.locator('.lv-stage').screenshot({ path: path.join(output, 'eight-gpus.png') });
  assert.equal(await page.locator('.lv-link').count(), 8);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.waitForTimeout(100);
  assert.equal(await page.locator('.lv-packet').count(), 0);
  assert.deepEqual(errors, []);
  await fs.writeFile(
    path.join(output, 'receipt.json'),
    JSON.stringify(
      {
        fixtureOnly: true,
        directFirstRow: true,
        readableDeviceNames: true,
        gpuModels: true,
        identifiersInTooltips: true,
        multiRow: true,
        responsive: true,
        reducedMotion: true,
      },
      null,
      2,
    ) + '\n',
  );
  console.log('PASS: direct connectors, named GPUs, multiple rows, responsive layout and reduced motion');
} finally {
  await browser.close();
}
