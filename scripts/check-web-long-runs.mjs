/** Read-only browser checks for the two recorded overnight soaks. No GPU work is submitted. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';

const [base, output, ...flags] = process.argv.slice(2);
const sessionPath = flags[flags.indexOf('--session-file') + 1];
const captureOnly = flags.includes('--capture-only');
if (!base || !output || (new URL(base).hostname !== '127.0.0.1' && !flags.includes('--session-file')))
  throw Error(
    'Use a disposable loopback fixture lab, or explicitly supply a saved session for read-only public checks',
  );
await fs.mkdir(output, { recursive: false });
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, locale: 'en-US' });
  const errors = [];
  const eventRequests = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('request', (request) => {
    if (request.url().includes('/api/v1/events')) eventRequests.push(request.url());
  });
  if (flags.includes('--session-file')) {
    const session = JSON.parse(await fs.readFile(sessionPath, 'utf8'));
    await page.addInitScript(({ token, workspace }) => {
      sessionStorage.setItem('heteroes.access-token', token);
      sessionStorage.setItem('heteroes.demo-workspace', workspace);
    }, session);
  } else {
    await page.goto(base + '/login');
    await page.locator('input[autocomplete="username"]').fill('admin');
    await page.locator('input[autocomplete="current-password"]').fill('test-admin-pass');
    await page.locator('form button[type="submit"]').click();
    await page.waitForURL((url) => !url.pathname.startsWith('/login'));
  }
  const results = [];
  for (const [kind, id, generation, candidates] of [
    ['completed', '44e65d7b2975447fa15fe85f115bad92', '600/600', '14400/14400'],
    ['failed', 'f10720536eba436ba026d650edbb6f16', '61/900', '1464/21600'],
  ]) {
    await page.goto(`${base}/experiments/${id}`);
    await page.locator('.detail-summary').waitFor();
    const summary = page.locator('.detail-summary').locator('..');
    await summary.screenshot({ path: path.join(output, `${kind}-overview.png`) });
    if (!captureOnly) {
      const axisLabels = page.locator('.reward-axis text');
      assert.ok(
        (await axisLabels.count()) > 0 && (await axisLabels.count()) <= 10,
        'long-run reward labels must remain readable',
      );
      const alerts = await page.locator('.experiment-management [role="alert"]').allInnerTexts();
      if (kind === 'completed') {
        assert.equal(alerts.length, 0, 'a completed run must not show a stale shutdown failure');
        assert.match(await summary.innerText(), /720\s*\/\s*722/);
        assert.match(await summary.innerText(), /Audits not completed: 2/);
      } else
        assert.ok(
          alerts.some((text) => text.includes('No space left on device')),
          'preserve the real disk-full failure',
        );
      assert.ok(
        eventRequests.some((url) => url.includes(`experimentId=${id}`)),
        'event history must be scoped before the server limit',
      );
    }
    await page.getByRole('tab', { name: 'Live and replay' }).click();
    await page.locator('.lv-diagram').waitFor();
    if (!captureOnly) {
      await page.waitForFunction(
        (expected) =>
          document.querySelector('.lv-stats > div:nth-child(2) b')?.textContent.replace(/\s/g, '') === expected,
        candidates,
      );
      const values = await page.locator('.lv-stats b').allInnerTexts();
      assert.equal(values[0].replace(/\s/g, ''), generation);
      assert.equal(values[1].replace(/\s/g, ''), candidates);
      assert.equal(
        await page.getByRole('button', { name: 'Play', exact: true }).count(),
        1,
        'open a partial replay at the stopped end',
      );
      assert.ok(
        (await page.locator('.lv-table tbody td:nth-child(2)').allInnerTexts()).every((text) => text === 'Stopped'),
      );
      assert.equal(await page.locator('.lv-history-note').count(), 1);
      assert.ok((await page.locator('.lv-band text').count()) <= 16);
      if (kind === 'completed')
        assert.ok((await page.locator('.lv-band').count()) <= 10, 'focus on six available generations');
      await page.locator('.lv-range select').selectOption('all');
      assert.ok((await page.locator('.lv-band text').count()) <= 16, 'full-history labels must not overlap');
      await page.locator('.lv-range select').selectOption('recent');
      if (kind === 'failed') assert.equal(await page.locator('.lv-ribbon .stopped').count(), 1);
    }
    await page.locator('.lv').screenshot({ path: path.join(output, `${kind}-live.png`) });
    if (!captureOnly)
      for (const width of [375, 768, 1440]) {
        await page.setViewportSize({ width, height: 1000 });
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
      }
    results.push({ kind, runId: id, checked: !captureOnly });
  }
  assert.deepEqual(errors, []);
  await fs.writeFile(
    path.join(output, 'receipt.json'),
    JSON.stringify({ readOnly: true, results, pageErrors: errors }, null, 2) + '\n',
  );
  console.log(
    captureOnly
      ? 'Captured both public runs before repair.'
      : 'PASS: both long runs, audit coverage, stopped state, totals, history scope and responsive charts',
  );
} finally {
  await browser.close();
}
