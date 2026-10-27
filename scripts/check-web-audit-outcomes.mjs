/**
 * Browser contract for audit outcomes on the experiment page, against the test lab seeded with outcome variants:
 *   python3 scripts/serve-test-lab.py --web <build> --port 18096 --audit-outcomes backend/tests/fixtures/audit-outcomes.json &
 *   node scripts/check-web-audit-outcomes.mjs http://127.0.0.1:18096 <fresh evidence directory>
 * Covers zero rate, nothing chosen, no auditor, timeout, historical partial evidence and a strict stop, in English
 * and Vietnamese. Fixture data only: it shows what the page says for these outcomes, not that a real run produced them.
 */
import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
const [base, output] = process.argv.slice(2);
if (!base || !output) throw Error('usage: check-web-audit-outcomes.mjs <base url> <fresh evidence directory>');
await fs.mkdir(output, { recursive: true });
const receipt = path.join(output, 'web-audit-outcomes.json');
try {
  await fs.access(receipt);
  throw Error('Evidence already exists');
} catch (error) {
  if (error.code !== 'ENOENT') throw error;
}

// [run name, English lines that must be shown with their tone, Vietnamese line that must be shown]
const CASES = [
  ['Audit fixture: zero rate', [['Audits are disabled (rate 0)', 'warn']], 'Đã tắt audit (tỷ lệ 0)'],
  [
    'Audit fixture: nothing chosen',
    [
      ['Audit outcomes: 0 chosen', 'warn'],
      ['No candidate has been chosen for audit yet; this is not evidence that results were checked.', 'warn'],
    ],
    'Chưa có candidate nào được chọn để audit',
  ],
  ['Audit fixture: no auditor', [['Audit outcomes: 8 chosen · 8 skipped', 'warn']], '8 bỏ qua'],
  ['Audit fixture: timeout', [['Audit outcomes: 8 chosen · 5 matched · 3 timed out', 'warn']], '3 hết thời gian'],
  [
    'Audit fixture: historical partial',
    [
      ['Audit outcomes: 8 chosen · 4 matched · 4 unknown', 'warn'],
      ['Some audit evidence is missing or from an older run; unknown is not a match.', 'warn'],
    ],
    '"không rõ" không có nghĩa là khớp',
  ],
  [
    'Audit fixture: strict stop',
    [
      ['Audit outcomes: 4 chosen · 1 mismatched · 3 unknown', 'err'],
      ['Strict decoder: the first audit mismatch stops the run before the next update.', 'info'],
      [
        'Strict audit mismatch on fixture/g0/c2 (generation 1): worker-a and worker-b produced different text. The run stopped before the next update and needs operator review.',
        'err',
      ],
    ],
    'Run đã dừng trước lần cập nhật kế tiếp',
  ],
];

const browser = await chromium.launch({ headless: true });
const results = {};
const errors = [];
try {
  for (const language of ['en', 'vi']) {
    const context = await browser.newContext({
      viewport: { width: 1280, height: 900 },
      locale: language === 'vi' ? 'vi-VN' : 'en-US',
    });
    await context.addInitScript(() => {
      globalThis.__HETEROES_I18N_AUDIT__ = true;
    });
    const page = await context.newPage();
    page.on('pageerror', (e) => errors.push(e.message));
    page.on('console', (m) => {
      if (m.type() === 'error' && !/status of (401|404)/.test(m.text())) errors.push(m.text());
    });
    await page.goto(base + '/login');
    await page.locator('input[autocomplete="username"]').fill('admin');
    await page.locator('input[autocomplete="current-password"]').fill('test-admin-pass');
    await page.locator('form button[type="submit"]').click();
    await page.waitForURL((u) => !u.pathname.startsWith('/login'));
    for (const [name, lines, vietnamese] of CASES) {
      await page.goto(base + '/experiments');
      await page.locator('a', { hasText: name }).first().click();
      await page.waitForURL((url) => /\/experiments\/[a-f0-9]{32}$/.test(url.pathname));
      const shown = page.locator('[data-audit-outcome]');
      await shown.first().waitFor();
      const texts = await shown.allTextContents();
      const tones = await shown.evaluateAll((nodes) => nodes.map((node) => node.dataset.auditOutcome));
      if (language === 'en') {
        assert.deepEqual(
          texts,
          lines.map(([text]) => text),
          name,
        );
        assert.deepEqual(
          tones,
          lines.map(([, tone]) => tone),
          name,
        );
        // a mismatch or stop is announced to assistive technology; other outcomes are not alerts
        const alerts = await shown.evaluateAll((nodes) => nodes.filter((node) => node.role === 'alert').length);
        assert.equal(alerts, tones.filter((tone) => tone === 'err').length, name);
      } else {
        assert.ok(
          texts.some((text) => text.includes(vietnamese)),
          `${name}: ${texts.join(' | ')}`,
        );
        assert.ok(!texts.some((text) => lines.some(([english]) => text === english)), `${name} untranslated`);
      }
      const slug = name.split(': ')[1].replaceAll(' ', '-');
      await page.screenshot({ path: path.join(output, `${language}-${slug}.png`), fullPage: true });
      results[`${language}:${name}`] = texts;
    }
    for (const width of [375, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      await page.waitForTimeout(300);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, 'overflow');
    }
    const missing = await page.evaluate(() => globalThis.__heteroesMissingI18n?.() ?? []);
    results[`${language}:untranslatedEnglishAudit`] = missing.length;
    assert.deepEqual(missing, [], 'untranslated strings');
    await context.close();
  }
  assert.deepEqual(errors, []);
  await fs.writeFile(
    receipt,
    JSON.stringify({ fixtureLab: true, realLab: false, gpuWork: false, ...results, browserErrors: errors }, null, 2) +
      '\n',
    { flag: 'wx' },
  );
  console.log('PASS audit outcomes contract (fixture lab, Chromium).');
} finally {
  await browser.close();
}
