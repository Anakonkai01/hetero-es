/**
 * Browser contract for the experiment tools (compare, run again, templates, exports) against the test lab seeded with two
 * recorded runs:
 *   python3 scripts/serve-test-lab.py --web <build> --port 18084 --seed-run backend/tests/fixtures/run-d09d6ea8.json --seed-run backend/tests/fixtures/run-95b34770.json --stuck-run backend/tests/fixtures/run-d09d6ea8.json &
 *   node scripts/check-web-experiments.mjs http://127.0.0.1:18084 <fresh evidence directory>
 */
import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
const [base, output] = process.argv.slice(2);
if (!base || !output) throw Error('usage: check-web-experiments.mjs <base url> <fresh evidence directory>');
await fs.mkdir(output, { recursive: true });
const receipt = path.join(output, 'web-experiments.json');
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
  const context = await browser.newContext({
    viewport: { width: 1280, height: 900 },
    locale: 'en-US',
    acceptDownloads: true,
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

  // The picker loads its templates after the page opens: wait for the option instead of reading the list at once.
  const choose = async (text) => {
    await page
      .waitForFunction(
        (needle) =>
          [...document.querySelectorAll('#template-picker option')].some((o) => o.textContent.includes(needle)),
        text,
        { timeout: 10000 },
      )
      .catch(() => {});
    const value = await page
      .locator('#template-picker option')
      .evaluateAll((options, needle) => options.find((o) => o.textContent.includes(needle))?.value, text);
    assert.ok(value, 'template option ' + text);
    await page.getByLabel('Start from').selectOption(value);
  };
  // 1. Pick two runs and compare them.
  await page.goto(base + '/experiments');
  await page.locator('.run-card').first().waitFor();
  await page.getByText('Compare', { exact: true }).first().waitFor();
  const picks = page.locator('.compare-pick-card input');
  assert.ok((await picks.count()) >= 2);
  await picks.nth(0).check();
  await page.getByText('1 selected · pick one more').waitFor();
  assert.equal(await page.locator('.compare-bar .btn.pri').isDisabled(), true);
  await picks.nth(1).check();
  await page.getByText('2 selected').waitFor();
  assert.equal(await page.locator('.compare-bar .btn.pri').isDisabled(), false);
  results.selectionBar = true;
  await page.locator('.compare-bar .btn.pri').click();
  await page.waitForURL('**/experiments/compare?ids=*');
  await page.locator('.compare-chart').waitFor();
  await page.getByRole('heading', { name: 'What was different' }).waitFor();
  assert.equal(await page.locator('.compare-legend li').count(), 2);
  results.compareShowsTwoRuns = true;
  assert.ok((await page.locator('.compare-chart path').count()) >= 4, 'two series, mean and best');
  results.compareChartDrawn = true;
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Table (CSV)' }).click();
  const file = await download;
  assert.equal(file.suggestedFilename(), 'comparison.csv');
  const csv = await fs.readFile(await file.path(), 'utf8');
  assert.match(csv.split('\n')[0], /^run,status,best_reward/);
  assert.equal(csv.trim().split('\n').length, 3);
  results.compareCsv = true;
  await page.screenshot({ path: path.join(output, 'compare.png'), fullPage: true });
  await page.goto(base + '/experiments/compare?ids=only-one');
  await page.getByText('Pick at least two experiments').waitFor();
  results.needsTwoRuns = true;

  // 2. A run: export, save as template, run again.
  await page.goto(base + '/experiments');
  await page.locator('a', { hasText: 'M2 three GPU agent acceptance v2' }).first().click();
  await page.getByRole('button', { name: 'Run again like this' }).waitFor();
  const csvDownload = page.waitForEvent('download');
  await page.getByText('Export ▾').click();
  await page.getByRole('menuitem', { name: 'Generations (CSV)' }).click();
  const generations = await csvDownload;
  assert.match(generations.suggestedFilename(), /generations\.csv$/);
  const text = await fs.readFile(await generations.path(), 'utf8');
  assert.match(text, /^generation,status,candidates,committed,reward_mean,reward_best/);
  assert.equal(text.trim().split('\n').length, 4);
  results.generationsCsv = true;
  const png = page.waitForEvent('download');
  await page.getByText('Export ▾').click();
  await page.getByRole('menuitem', { name: 'Reward chart (PNG)' }).click();
  const image = await png;
  const bytes = await fs.readFile(await image.path());
  assert.equal(bytes.subarray(1, 4).toString(), 'PNG');
  results.chartPng = true;
  const md = page.waitForEvent('download');
  await page.getByText('Export ▾').click();
  await page.getByRole('menuitem', { name: 'One-page summary (Markdown)' }).click();
  const summary = await md;
  assert.match(await fs.readFile(await summary.path(), 'utf8'), /^# M2 three GPU agent acceptance v2/);
  results.markdownSummary = true;

  await page.getByRole('button', { name: 'Save settings as template' }).click();
  await page.getByLabel('Template name').fill('Three GPU 3x12');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await page.getByText('Template saved.').waitFor();
  results.templateSaved = true;
  await page.getByRole('button', { name: 'Run again like this' }).click();
  await page.waitForURL('**/experiments/new');
  assert.equal(await page.getByLabel('Experiment name').inputValue(), 'M2 three GPU agent acceptance v2 (copy)');
  assert.equal(await page.getByLabel('Candidates per generation').inputValue(), '12');
  assert.equal(await page.getByLabel('Maximum generations').inputValue(), '3');
  results.runAgainPrefills = true;
  await choose('Three GPU 3x12');
  assert.equal(await page.getByLabel('Experiment name').inputValue(), 'Three GPU 3x12');
  assert.equal(await page.getByLabel('Candidates per generation').inputValue(), '12');
  results.savedTemplateApplies = true;
  await choose('Quick smoke test');
  assert.equal(await page.getByLabel('Candidates per generation').inputValue(), '4');
  assert.equal(await page.getByLabel('Experiment name').inputValue(), '');
  results.builtInTemplateApplies = true;
  await page.screenshot({ path: path.join(output, 'create-from-template.png'), fullPage: true });
  page.once('dialog', (d) => d.accept());
  await choose('Three GPU 3x12');
  await page.getByRole('button', { name: 'Delete template' }).click();
  await page.waitForFunction(
    () =>
      ![...document.querySelectorAll('#template-picker option')].some((o) => o.textContent.includes('Three GPU 3x12')),
  );
  results.templateDeleted = true;

  // Recipe v3: imported columns and a real draft through the browser against this disposable CPU lab.
  // The compatibility declarations below are synthetic fixture data, never hardware acceptance.
  const auth = await page.evaluate(() => sessionStorage.getItem('heteroes.access-token'));
  const headers = { Authorization: `Bearer ${auth}`, 'X-Workspace-Id': 'lab' };
  const post = async (url, data) => {
    const response = await page.request.post(base + url, { headers, data });
    assert.ok(response.ok(), `${url}: ${response.status()}`);
    return response.json();
  };
  const manifest = {
    formatVersion: 1,
    modelId: 'fixture/custom-model',
    revision: 'a'.repeat(40),
    tokenizerRevision: 'a'.repeat(40),
    format: 'safetensors',
    files: { 'config.json': 'b'.repeat(64), 'model.safetensors': 'c'.repeat(64), 'tokenizer.json': 'd'.repeat(64) },
  };
  const canonical = (value) =>
    JSON.stringify(
      value && typeof value === 'object' && !Array.isArray(value)
        ? Object.fromEntries(
            Object.keys(value)
              .sort()
              .map((k) => [k, JSON.parse(canonical(value[k]))]),
          )
        : value,
    );
  const modelHash = createHash('sha256').update(canonical(manifest)).digest('hex');
  const model = await post('/api/v1/models/register', { name: 'V3 fixture model', recipeVersion: 3, manifest });
  const pairing = await post('/api/v1/devices/pairing-codes', {});
  const enrolled = await post('/api/v1/device/enroll', {
    code: pairing.code,
    workerId: 'v3-fixture',
    displayName: 'V3 fixture',
    computeUrl: 'http://127.0.0.1:18769',
    selfTest: {
      passed: true,
      coordinator: true,
      gpuName: 'CPU fixture (no GPU computation)',
      vramTotalMb: 1024,
      noiseVersion: 'numpy_pcg64_normal_f32_to_f16_v1',
      gpuUUID: 'GPU-00000000-0000-4000-8000-000000000003',
      recipeVersions: [3],
      qualifiedModelHashes: [modelHash],
      compatibility: {
        recipeV3: {
          passed: true,
          repeatIdentical: true,
          modelManifestHash: modelHash,
          recipeHash: 'a'.repeat(64),
          parentSha256: 'b'.repeat(64),
          restoredSha256: 'b'.repeat(64),
          perturbedSha256: 'c'.repeat(64),
          outputsHash: 'd'.repeat(64),
        },
      },
    },
  });
  const approved = await page.request.patch(base + '/api/v1/platform/devices/' + enrolled.deviceId, {
    headers,
    data: { approved: true, workspaceId: 'lab' },
  });
  assert.ok(approved.ok());
  const defaultCoordinator = await page.request.patch(base + '/api/v1/workspaces/lab/default-coordinator', {
    headers,
    data: { deviceId: enrolled.deviceId },
  });
  assert.ok(defaultCoordinator.ok());
  await page.goto(base + '/models');
  await page.getByLabel('Asset recipe').selectOption('3');
  await page.getByText('Import dataset', { exact: true }).first().click();
  await page.getByLabel('Dataset name').fill('V3 arbitrary columns');
  await page.getByLabel('Prompt field').fill('question');
  const rows = Array.from({ length: 20 }, (_, i) => ({ question: `Question ${i}`, label: 'A', level: i }));
  await page
    .locator('input[type="file"][accept=".json,.jsonl,.csv"]')
    .setInputFiles({ name: 'v3.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(rows)) });
  await page.getByRole('button', { name: 'Import dataset', exact: true }).click();
  await page.getByText('Saved and verified.', { exact: true }).waitFor();
  const datasets = await (await page.request.get(base + '/api/v1/datasets', { headers })).json();
  const dataset = datasets.find((d) => d.name === 'V3 arbitrary columns');
  assert.ok(dataset.columns.includes('label') && dataset.columns.includes('level'));
  await page.goto(base + '/experiments/new');
  // a notebook creates experiments (owner 2026-10-22); the web form stays one click away
  await page.getByRole('heading', { name: 'Create an experiment from a notebook' }).waitFor();
  assert.equal(await page.getByLabel('Experiment recipe').isVisible(), false);
  results.notebookGuideFirst = true;
  await page.getByText('Or use the web form', { exact: false }).click();
  await page.getByLabel('Experiment recipe').selectOption('3');
  await page.getByLabel('Experiment name', { exact: true }).fill('V3 browser draft');
  await page.getByLabel('Pinned model').selectOption(model.modelArtifactId);
  await page.getByLabel('Frozen dataset').selectOption(dataset.datasetId);
  await page.getByLabel('Batch size', { exact: true }).fill('4');
  await page.getByLabel('Weight space').selectOption('lora');
  await page.getByLabel('LoRA rank', { exact: true }).fill('4');
  await page.getByLabel('Antithetic sampling', { exact: true }).check();
  await page.getByLabel('Candidate seed group', { exact: true }).fill('browser-baseline');
  await page.getByRole('combobox', { name: /^Scorer/ }).selectOption('choice-letter');
  await page.getByLabel('Scorer answer field').fill('label');
  await page.getByRole('button', { name: 'Continue', exact: true }).click();
  assert.equal(await page.getByLabel('Coordinator').inputValue(), enrolled.deviceId);
  // Clearing the selection is a user choice, including after leaving and returning to this step.
  await page.getByLabel('Coordinator').selectOption('');
  await page.getByRole('button', { name: 'Back', exact: true }).click();
  await page.getByRole('button', { name: 'Continue', exact: true }).click();
  assert.equal(await page.getByLabel('Coordinator').inputValue(), '');
  await page.getByLabel('Coordinator').selectOption(enrolled.deviceId);
  results.defaultCoordinatorAndManualChoice = true;
  await page.getByLabel(/CPU fixture/).check();
  await page.getByRole('button', { name: 'Continue', exact: true }).click();
  await page.getByRole('button', { name: 'Save draft', exact: true }).click();
  await page.waitForURL((url) => /\/experiments\/[a-f0-9]{32}$/.test(url.pathname));
  const v3 = await (
    await page.request.get(base + '/api/v1/experiments/' + page.url().split('/').at(-1), { headers })
  ).json();
  assert.equal(v3.recipeVersion, 3);
  assert.equal(v3.modelVersion, manifest.revision);
  assert.equal(v3.weightSpace.kind, 'lora');
  assert.equal(v3.weightSpace.rank, 4);
  assert.equal(v3.scorer.config.answerField, 'label');
  assert.equal(v3.antithetic, true);
  assert.equal(v3.candidateSeedNamespace, 'browser-baseline');
  assert.equal(v3.systemPrompt, null);
  await page.getByRole('tab', { name: 'Configuration', exact: true }).click();
  await page.getByText('choice-letter@1', { exact: true }).waitFor();
  await page.getByText('lora', { exact: true }).waitFor();
  results.v3ImportAndBrowserDraft = true;
  await page.screenshot({ path: path.join(output, 'v3-draft.png'), fullPage: true });

  // A run that cannot start says why, from what its coordinator device reported (not from the run snapshot).
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(base + '/experiments');
  await page.locator('a', { hasText: 'Run that cannot start' }).first().click();
  const waiting = page
    .getByRole('status')
    .filter({ hasText: 'This device is waiting: contribution is switched off on it' });
  await waiting.waitFor();
  assert.match(await waiting.textContent(), /switched off on it · .*\d/);
  assert.equal(await waiting.getAttribute('class'), 'note warn');
  await page.getByRole('tab', { name: 'Logs' }).click();
  await page.getByText('This device is waiting: contribution is switched off on it').nth(1).waitFor();
  await page.screenshot({ path: path.join(output, 'run-that-cannot-start.png'), fullPage: true });
  results.stuckRunShowsWhyItWaits = true;

  for (const width of [375, 768, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    for (const url of ['/experiments', '/experiments/compare?ids=a,b']) {
      await page.goto(base + url);
      await page.waitForTimeout(500);
      assert.equal(
        await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
        false,
        `overflow ${url} ${width}`,
      );
    }
  }
  results.noOverflow = true;
  const missing = await page.evaluate(() => globalThis.__heteroesMissingI18n?.() ?? []);
  results.untranslatedEnglishAudit = missing.length;
  assert.deepEqual(errors, []);
  await fs.writeFile(
    receipt,
    JSON.stringify({ fixtureLab: true, realLab: false, gpuWork: false, ...results, browserErrors: errors }, null, 2) +
      '\n',
    { flag: 'wx' },
  );
  console.log('PASS experiment tools contract (fixture lab, Chromium).');
} finally {
  await browser.close();
}
