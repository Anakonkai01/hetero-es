/** Runs against the manually started private deployment; acquires the local GPU briefly. */
import assert from "node:assert/strict";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { chromium } from "playwright";

const privateRoot = process.env.HETEROES_PRIVATE_CONFIG ?? path.join(os.homedir(), ".config/heteroes-integration");
const config = JSON.parse(await readFile(path.join(privateRoot, "config.json"), "utf8"));
const credentials = JSON.parse(await readFile(path.join(privateRoot, "credentials.json"), "utf8"));
const url = process.env.HETEROES_UI_URL ?? `http://${config.uiHost}:5173`;
const output = path.join(config.productStateDirectory, "browser-evidence");
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function signIn(username) {
  await page.goto(url + "/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password", { exact: true }).fill(credentials.users[username]);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/workspace");
}
async function api(route) {
  const token = await page.evaluate(() => sessionStorage.getItem("heteroes.access-token"));
  const response = await context.request.get(url + "/api/v1" + route, { headers: { Authorization: `Bearer ${token}`, "X-Workspace-Id": "lab" } });
  assert.equal(response.status(), 200);
  return response.json();
}
async function until(operation, seconds = 180) {
  const deadline = Date.now() + seconds * 1000;
  while (Date.now() < deadline) {
    const result = await operation();
    if (result) return result;
    await sleep(1000);
  }
  throw new Error("Timed out waiting for real runtime progress");
}

try {
  await signIn("admin");
  const completed = (await api("/experiments")).find((run) => run.status === "COMPLETED" &&
    (!process.env.HETEROES_OBSERVE_RUN_ID || run.experimentId === process.env.HETEROES_OBSERVE_RUN_ID));
  assert.ok(completed, "Complete a runtime smoke run before browser acceptance");
  await page.goto(url + `/experiments/${completed.experimentId}`);
  await page.getByRole("heading", { name: "Runtime results" }).waitFor();
  assert.equal(await page.getByText("Simulated figures — no model is evaluated").count(), 0);
  assert.equal(await page.getByRole("button", { name: "Pause / resume" }).isDisabled(), true);
  assert.equal(await page.getByRole("button", { name: "Change workers during run" }).isDisabled(), true);
  const downloadable = (await api("/artifacts")).find((item) => item.experimentId === completed.experimentId && item.name.startsWith("summary-"));
  assert.ok(downloadable);
  const downloadEvent = page.waitForEvent("download");
  await page.locator(".demo-item").filter({ hasText: downloadable.name }).getByRole("button", { name: "Download", exact: true }).click();
  const downloaded = await downloadEvent;
  await downloaded.saveAs(path.join(output, "downloaded-summary.json"));
  assert.equal(JSON.parse(await readFile(path.join(output, "downloaded-summary.json"), "utf8")).status, "COMPLETED");
  await page.screenshot({ path: path.join(output, "completed-runtime.png"), fullPage: true });
  const generations = await api(`/experiments/${completed.experimentId}/generations`);
  const candidates = await api(`/generations/${generations[0].generationId}/candidates`);
  await page.goto(url + `/experiments/${completed.experimentId}/generations/${generations[0].generationId}/candidates/${candidates[0].candidateId}`);
  await page.getByText("Technical details", { exact: true }).click();
  await page.getByText(candidates[0].seed, { exact: true }).waitFor();
  await page.goto(url + "/workers");
  await page.getByRole("heading", { name: "Workers", exact: true }).waitFor();
  assert.equal(await page.getByRole("button", { name: "Register worker" }).isDisabled(), true);
  await page.screenshot({ path: path.join(output, "worker-inventory.png"), fullPage: true });
  if (process.argv.includes("--observe-only")) {
    assert.deepEqual(errors, []);
    await writeFile(path.join(output, "observation.json"), JSON.stringify({ completedRunId: completed.experimentId,
      authenticatedSummaryDownload: true, exactCandidateSeed: true, browserErrors: errors }, null, 2));
    console.log("PASS real browser observation, exact seed display, disabled controls and authenticated artifact download");
  } else {
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.waitForURL("**/login");

  await signIn("participant");
  assert.equal((await api("/experiments")).some((run) => run.experimentId === completed.experimentId), false);
  await page.goto(url + "/experiments/new");
  await page.getByLabel("Experiment name").fill("Browser acceptance cancellation");
  await page.getByRole("checkbox", { name: /5070ti/ }).check();
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await page.waitForURL(/\/experiments\/[a-f0-9]{32}$/);
  const runId = page.url().split("/").at(-1);
  await page.getByRole("button", { name: "Start experiment", exact: true }).click();
  await until(async () => {
    const run = await api(`/experiments/${runId}`);
    assert.notEqual(run.status, "FAILED");
    return run.completedGenerations >= 1;
  });
  await page.getByRole("button", { name: "Cancel experiment", exact: true }).click();
  const cancelled = await until(async () => {
    const run = await api(`/experiments/${runId}`);
    return run.status === "CANCELLED" && run;
  });
  assert.ok(cancelled.completedGenerations >= 1 && cancelled.completedGenerations < 3);
  const artifacts = (await api("/artifacts")).filter((item) => item.experimentId === runId);
  assert.ok(artifacts.some((item) => item.type === "CHECKPOINT"));
  await page.getByText("CANCELLED", { exact: true }).first().waitFor();
  await page.screenshot({ path: path.join(output, "cancelled-runtime.png"), fullPage: true });
  await writeFile(path.join(output, "acceptance.json"), JSON.stringify({ completedRunId: completed.experimentId,
    cancelledRunId: runId, completedGenerationsBeforeCancel: cancelled.completedGenerations, browserErrors: errors }, null, 2));
  assert.deepEqual(errors, []);
  console.log("PASS real login, workspace, rewards, candidate seed, worker inventory, role isolation, UI create/start/cancel and checkpoint preservation");
  console.log(`Evidence: ${output}`);
  }
} finally {
  await browser.close();
}
