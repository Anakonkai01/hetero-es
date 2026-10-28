// Read-only screenshots of the real lab's acceptance run; the session token is injected, never printed or saved.
import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
const [base, run, out] = process.argv.slice(2);
const s = JSON.parse(await fs.readFile(path.join(os.homedir(), '.config/heteroes-demo/session.json'), 'utf8'));
await fs.mkdir(out, { recursive: true });
const browser = await chromium.launch();
const result = [];
for (const [width, height] of [[1440, 900], [768, 1024], [375, 812]]) {
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript(([t, w]) => {
    sessionStorage.setItem('heteroes.access-token', t);
    if (w) sessionStorage.setItem('heteroes.demo-workspace', w);
  }, [s.token, s.workspace ?? '']);
  const page = await context.newPage();
  const errors = [];
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text().slice(0, 200)));
  await page.goto(`${base}/experiments/${run}`, { waitUntil: 'domcontentloaded', timeout: 90000 });
  await page.waitForTimeout(8000);
  await page.screenshot({ path: path.join(out, `run-${width}.png`), fullPage: false });
  const tab = page.getByRole('tab', { name: /live|trực tiếp|phát lại|replay/i }).first();
  let tabFound = false;
  if (await tab.count()) { tabFound = true; await tab.click(); await page.waitForTimeout(4000); }
  await page.screenshot({ path: path.join(out, `live-replay-${width}.png`), fullPage: false });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  const title = await page.title();
  result.push({ width, title, tabFound, horizontalOverflowPx: overflow, consoleErrors: errors, url: page.url().replace(base, '') });
  await context.close();
}
await browser.close();
await fs.writeFile(path.join(out, 'web-final.json'), JSON.stringify(result, null, 2));
console.log(JSON.stringify(result));
