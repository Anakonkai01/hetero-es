/**
 * Browser contract for the demo features: How it works page, Ctrl+K palette, presentation mode and tour, home-page replay.
 *   python3 scripts/serve-test-lab.py --web <build> --port 18087 --seed-run backend/tests/fixtures/run-d09d6ea8.json --seed-run backend/tests/fixtures/run-95b34770.json &
 *   node scripts/check-web-showcase.mjs http://127.0.0.1:18087 <fresh evidence directory>
 */
import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
const [base, output] = process.argv.slice(2);
if (!base || !output) throw Error('usage: check-web-showcase.mjs <base url> <fresh evidence directory>');
await fs.mkdir(output, { recursive: true });
const receipt = path.join(output, 'web-showcase.json');
try {
  await fs.access(receipt);
  throw Error('Evidence already exists');
} catch (error) {
  if (error.code !== 'ENOENT') throw error;
}
const browser = await chromium.launch({ headless: true });
const results = {};
const errors = [];
try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, locale: 'en-US' });
  await context.addInitScript(() => {
    globalThis.__HETEROES_I18N_AUDIT__ = true;
  });
  const page = await context.newPage();
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => {
    if (m.type() === 'error' && !/status of (401|404)/.test(m.text())) errors.push(m.text());
  });

  // 1. How it works: five steps, real numbers, keyboard.
  await page.goto(base + '/explain');
  await page.getByRole('heading', { name: 'Training a model by trial and selection' }).waitFor();
  await page.getByRole('heading', { name: 'Start from the model you have' }).waitFor();
  await page.keyboard.press('ArrowRight');
  await page.getByRole('heading', { name: 'Nudge it at random, many times' }).waitFor();
  await page.getByText('This run made 12 candidates per generation.').waitFor();
  results.stepsFollowTheKeyboard = true;
  await page.getByRole('button', { name: 'Next →' }).click();
  await page.getByText('3 different GPUs shared the work').waitFor();
  assert.equal(await page.locator('.explain-bars li').count(), 12);
  results.realRewardsListed = true;
  await page.locator('abbr.term').first().focus();
  assert.match(await page.locator('abbr.term').first().getAttribute('data-definition'), /.+/);
  results.termsHaveDefinitions = true;
  await page.getByRole('button', { name: 'Next →' }).click();
  await page.getByRole('button', { name: 'Next →' }).click();
  await page.getByRole('link', { name: 'See it live →' }).waitFor();
  results.endsWithALink = true;
  await page.screenshot({ path: path.join(output, 'explain.png'), fullPage: true });

  // 2. The home page replays a real run.
  await page.goto(base + '/');
  await page.locator('.demo-replay').waitFor();
  await page.getByText('A real run from this lab, replayed').first().waitFor();
  await page.waitForFunction(() => document.querySelectorAll('.demo-replay .hero-gpu').length === 3);
  results.homeReplaysThreeGpus = true;

  // 3. Sign in, open the palette with Ctrl+K and use it.
  await page.goto(base + '/login');
  await page.locator('input[autocomplete="username"]').fill('admin');
  await page.locator('input[autocomplete="current-password"]').fill('test-admin-pass');
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL((u) => !u.pathname.startsWith('/login'));
  await page.goto(base + '/dashboard');
  await page.locator('.control-room').waitFor();
  await page.keyboard.press('Control+k');
  const box = page.locator('.palette > input');
  await box.waitFor();
  assert.equal(await box.evaluate((el) => document.activeElement === el), true);
  results.paletteOpensFocused = true;
  await box.fill('thre');
  await page.getByRole('option', { name: /M2 three GPU agent acceptance v2/ }).waitFor();
  await page.keyboard.press('Enter');
  await page.waitForURL(/\/experiments\/[0-9a-f]{32}$/);
  results.paletteOpensAnExperiment = true;
  await page.keyboard.press('Control+k');
  await box.fill('how');
  await page.keyboard.press('Enter');
  await page.waitForURL('**/explain');
  results.paletteOpensAPage = true;
  await page.goto(base + '/dashboard');
  await page.locator('.control-room').waitFor();
  await page.keyboard.press('Control+k');
  await box.fill('zzzz');
  await page.getByText('Nothing matches').waitFor();
  await page.keyboard.press('Escape');
  await box.waitFor({ state: 'detached' });
  results.escapeCloses = true;
  await page.keyboard.press('Control+k');
  await box.fill('Tiếng');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.documentElement.lang === 'vi');
  results.paletteSwitchesLanguage = true;
  await page.keyboard.press('Control+k');
  await box.fill('English');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.documentElement.lang === 'en');
  await page.waitForTimeout(300);

  // 4. Presentation mode: bigger, no technical ids, a tour with the arrow keys, Escape leaves.
  await page.goto(base + '/experiments');
  await page.locator('a', { hasText: 'M2 three GPU agent acceptance v2' }).first().click();
  await page.locator('.tech').first().waitFor();
  assert.equal(await page.locator('.tech').first().isVisible(), true);
  await page.getByRole('button', { name: /Present/ }).click();
  await page.locator('.presentation-bar').waitFor();
  assert.equal(await page.locator('.tech').first().isVisible(), false, 'technical ids are hidden while presenting');
  results.presentationHidesIds = true;
  assert.equal(await page.evaluate(() => document.documentElement.dataset.present), '1');
  await page.getByRole('button', { name: /1 · Control room/ }).click();
  await page.waitForURL('**/dashboard');
  await page.locator('.control-room').waitFor();
  await page.keyboard.press('ArrowRight');
  await page.waitForURL((url) => /\/experiments\/[0-9a-f]{32}\?tab=live$/.test(url.pathname + url.search));
  await page.locator('.lv').waitFor();
  results.tourReachesTheLiveScene = true;
  await page.keyboard.press('ArrowRight');
  await page.waitForURL('**/experiments/compare?ids=*');
  results.tourReachesComparison = true;
  await page.keyboard.press('ArrowRight');
  await page.waitForURL('**/explain');
  results.tourEndsWithTheExplanation = true;
  await page.screenshot({ path: path.join(output, 'presentation-explain.png') });
  await page.goto(base + '/dashboard');
  await page.locator('.control-room').waitFor();
  await page.keyboard.press('Escape');
  await page.locator('.presentation-bar').waitFor({ state: 'detached' });
  results.escapeLeavesPresentation = true;

  for (const width of [375, 768, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    for (const url of ['/explain', '/']) {
      await page.goto(base + url);
      await page.waitForTimeout(400);
      assert.equal(
        await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
        false,
        `overflow ${url} ${width}`,
      );
    }
  }
  results.noOverflow = true;
  assert.deepEqual(errors, []);
  await fs.writeFile(
    receipt,
    JSON.stringify({ fixtureLab: true, realLab: false, gpuWork: false, ...results, browserErrors: errors }, null, 2) +
      '\n',
    { flag: 'wx' },
  );
  console.log('PASS showcase contract (fixture lab, Chromium).');
} finally {
  await browser.close();
}
