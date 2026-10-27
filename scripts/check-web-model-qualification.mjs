/** Model compatibility controls against a disposable CPU lab. Synthetic reports are never GPU acceptance. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';
const [base, output] = process.argv.slice(2);
if (!base || !output) throw Error('usage: check-web-model-qualification.mjs <fixture lab> <fresh evidence directory>');
await fs.mkdir(output, { recursive: false });
const browser = await chromium.launch({ headless: true });
const results = { syntheticCpuFixture: true };
try {
  const context = await browser.newContext({ locale: 'en-US' });
  await context.addInitScript(() => {
    globalThis.__HETEROES_I18N_AUDIT__ = true;
  });
  const page = await context.newPage();
  await page.goto(base + '/login');
  await page.locator('input[autocomplete="username"]').fill('admin');
  await page.locator('input[autocomplete="current-password"]').fill('test-admin-pass');
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL((u) => !u.pathname.startsWith('/login'));
  const token = await page.evaluate(() => sessionStorage.getItem('heteroes.access-token'));
  const headers = { Authorization: `Bearer ${token}`, 'X-Workspace-Id': 'lab' };
  const post = async (url, data, auth = headers) => {
    const response = await page.request.post(base + url, { headers: auth, data });
    assert.ok(response.ok(), `${url}: ${response.status()}`);
    return response.json();
  };
  const manifest = {
    formatVersion: 1,
    modelId: 'fixture/new-model',
    revision: 'a'.repeat(40),
    tokenizerRevision: 'a'.repeat(40),
    format: 'safetensors',
    files: {
      'config.json': 'b'.repeat(64),
      'model.safetensors': 'c'.repeat(64),
      'tokenizer.json': 'd'.repeat(64),
    },
  };
  const model = await post('/api/v1/models/register', { recipeVersion: 3, name: 'New model for checking', manifest });
  const code = await post('/api/v1/devices/pairing-codes', {});
  const device = await post('/api/v1/device/enroll', {
    code: code.code,
    workerId: 'model-check-fixture',
    displayName: 'Model check computer',
    computeUrl: 'http://127.0.0.1:18769',
    selfTest: {
      passed: true,
      gpuName: 'CPU fixture only',
      vramTotalMb: 1024,
      noiseVersion: 'pcg64_u32_to_f16_normal_quantile_v2',
      supportedNoiseEngines: {
        pcg64_u32_to_f16_normal_quantile_v2: 'e80f079ca06fd3e2fcae7b41583aedd8b407e65c196677d5da54c1dc6de02bb4',
      },
      gpuUUID: 'GPU-00000000-0000-4000-8000-000000000009',
      recipeVersions: [3],
      qualifiedModelHashes: ['f'.repeat(64)],
      compatibility: {
        recipeV3: {
          passed: true,
          repeatIdentical: true,
          modelManifestHash: 'f'.repeat(64),
          recipeHash: 'a'.repeat(64),
          parentSha256: 'b'.repeat(64),
          restoredSha256: 'b'.repeat(64),
          perturbedSha256: 'c'.repeat(64),
          outputsHash: 'd'.repeat(64),
        },
      },
    },
  });
  assert.ok(
    (
      await page.request.patch(base + '/api/v1/platform/devices/' + device.deviceId, {
        headers,
        data: { approved: true, workspaceId: 'lab' },
      })
    ).ok(),
  );
  const auth = {
    Authorization: `Bearer ${device.deviceToken}`,
    'X-HeteroES-Agent-Commands':
      'SET_CONTRIBUTION,COORDINATE,START_WORKER,STOP_WORKER,CANCEL_ASSIGNMENT,QUALIFY_MODEL,CANCEL_MODEL_QUALIFICATION',
  };
  const poll = (changes = {}) =>
    post('/api/v1/device/poll', { bootId: 'fixture-boot', contribution: true, ...changes }, auth);
  await poll();
  await page.goto(base + '/models');
  const card = page.locator(`[data-model-id="${model.id}"]`);
  const select = card.getByLabel('Device for model check');
  await select.selectOption(device.deviceId);
  assert.equal(await card.getByRole('button', { name: 'Check compatibility', exact: true }).isDisabled(), true);
  await post('/api/v1/devices/' + device.deviceId + '/contribution', { enabled: true, bootId: 'fixture-boot' });
  await poll();
  await card.getByRole('button', { name: 'Check compatibility', exact: true }).click();
  await card.getByText('Preparing model check', { exact: true }).waitFor();
  const status = await (await page.request.get(base + `/api/v1/models/${model.id}/qualifications`, { headers })).json();
  const job = status.jobs[0];
  assert.equal(job.mode, 'BUILD_REFERENCE');
  const start = (await poll()).commands.find((c) => c.kind === 'QUALIFY_MODEL');
  assert.equal(start.jobId, job.jobId);
  assert.deepEqual(start.manifest, manifest);
  results.startedThroughUi = true;
  await card.getByRole('button', { name: 'Cancel model check', exact: true }).click();
  await card.getByText('Waiting for model check to stop', { exact: true }).waitFor();
  await poll({ qualificationReports: [{ jobId: job.jobId, status: 'CANCELLED', processAlive: null }] });
  await card.getByText('Waiting for model check to stop', { exact: true }).waitFor();
  await poll({ qualificationReports: [{ jobId: job.jobId, status: 'CANCELLED', processAlive: false }] });
  await card.getByText('Model check cancelled', { exact: true }).waitFor();
  results.cancelWaitedForConfirmedDeath = true;
  // M4: the strict decoder has its own check, with the new noise engine only
  await card.getByLabel(/^Decoder/).selectOption('strict_b22_v1');
  assert.equal(await card.getByLabel('Compatibility for').isDisabled(), true);
  await card.getByText('This computer needs a model check.').waitFor();
  await card.getByRole('button', { name: 'Check compatibility for the strict decoder', exact: true }).click();
  await card.getByText('Preparing model check', { exact: true }).waitFor();
  const strictStatus = await (
    await page.request.get(base + `/api/v1/models/${model.id}/qualifications`, { headers })
  ).json();
  const strictJob = strictStatus.jobs.find((j) => j.status !== 'CANCELLED');
  assert.equal(strictJob.decoder, 'strict_b22_v1');
  assert.equal(strictJob.mode, 'BUILD_REFERENCE');
  const strictStart = (await poll()).commands.find((c) => c.kind === 'QUALIFY_MODEL' && c.jobId === strictJob.jobId);
  assert.equal(strictStart.decoder, 'strict_b22_v1');
  assert.equal(strictStart.noiseEngineVersion, 'pcg64_u32_to_f16_normal_quantile_v2');
  await card.getByText('· strict decoder').waitFor();
  results.strictCheckStartedThroughUi = true;
  await page.screenshot({ path: path.join(output, 'model-check.png'), fullPage: true });
  const missing = await page.evaluate(() => globalThis.__HETEROES_MISSING_TRANSLATIONS__ ?? []);
  assert.deepEqual(missing, []);
  results.passed = true;
} catch (error) {
  results.passed = false;
  results.error = String(error.message);
  throw error;
} finally {
  await fs.writeFile(path.join(output, 'web-model-qualification.json'), JSON.stringify(results, null, 2), {
    flag: 'wx',
  });
  await browser.close();
}
