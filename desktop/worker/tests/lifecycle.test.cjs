// Quit / tray / startup behaviour of the Worker main process, tested without Electron.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { Lifecycle, describeCode } = require('../electron/lifecycle.cjs');
const { createLog } = require('@heteroes/desktop-shared/log.cjs');

function harness(serviceOverrides = {}) {
  const events = [];
  const service = {
    bridge: null,
    quit: async () => {
      events.push('service.quit');
      return { drained: true };
    },
    contribution: async (enabled) => {
      events.push('contribution:' + enabled);
      return { enabled };
    },
    ...serviceOverrides,
  };
  const lifecycle = new Lifecycle({
    service,
    quitApp: () => events.push('quitApp'),
    show: () => events.push('show'),
    notify: (title, body) => events.push('notify:' + body),
    fail: (title, body) => events.push('fail:' + body),
    log: {
      info() {},
      error(message, error) {
        events.push('log:' + message + ':' + (error?.message ?? ''));
      },
    },
  });
  return { lifecycle, service, events };
}
const gate = () => {
  let release;
  const promise = new Promise((resolve) => {
    release = resolve;
  });
  return { promise, release };
};

test('only one ordinary action runs at a time, and the gate is always released', async () => {
  const { lifecycle } = harness();
  const first = gate();
  const running = lifecycle.run('connect', () => first.promise);
  await assert.rejects(
    lifecycle.run('login', async () => 'x'),
    /ACTION_IN_PROGRESS/,
  );
  first.release('done');
  assert.equal(await running, 'done');
  await assert.rejects(
    lifecycle.run('login', async () => {
      throw Error('LAB_HTTP_401');
    }),
    /LAB_HTTP_401/,
  );
  assert.equal(await lifecycle.run('login', async () => 'again'), 'again');
});

test('Quit is never refused because another action is running; it exits once drained', async () => {
  const { lifecycle, events } = harness();
  const blocked = gate();
  const running = lifecycle.run('connect', () => blocked.promise);
  const state = await lifecycle.quit();
  assert.equal(state.drained, true);
  assert.deepEqual(events, ['service.quit', 'quitApp']);
  assert.equal(lifecycle.exiting, true);
  blocked.release();
  await running;
});

test('repeated Quit clicks run the shutdown once', async () => {
  const slow = gate();
  const { lifecycle, events } = harness({
    quit: async () => {
      events.push('service.quit');
      await slow.promise;
      return { drained: true };
    },
  });
  const clicks = [lifecycle.quit(), lifecycle.quit(), lifecycle.quit()];
  slow.release();
  await Promise.all(clicks);
  assert.equal(events.filter((e) => e === 'service.quit').length, 1);
  assert.equal(events.filter((e) => e === 'quitApp').length, 1);
});

test('once the app is leaving, another Quit does not start a second shutdown', async () => {
  const { lifecycle, events } = harness();
  await lifecycle.quit();
  assert.deepEqual(await lifecycle.quit(), { drained: true });
  assert.equal(events.filter((e) => e === 'service.quit').length, 1);
});

test('Quit that cannot confirm the drain keeps the app open and brings the window back', async () => {
  const { lifecycle, events } = harness({ quit: async () => ({ drained: false }) });
  assert.equal((await lifecycle.quit()).drained, false);
  assert.ok(events.includes('show'));
  assert.ok(!events.includes('quitApp'));
  assert.equal(lifecycle.exiting, false);
});

test('a failed tray Quit tells the user why; it never just reopens the window', async () => {
  const { lifecycle, events } = harness({
    quit: async () => {
      throw Error('SETUP_IN_PROGRESS');
    },
  });
  await lifecycle.userQuit();
  assert.ok(events.includes('show'));
  const message = events.find((e) => e.startsWith('notify:'));
  assert.match(message, /SETUP_IN_PROGRESS/);
  assert.match(message, /runtime|môi trường/i);
  assert.ok(events.some((e) => e.startsWith('log:')));
  assert.ok(!events.includes('quitApp'));
});

test('a tray Quit that cannot confirm the drain also says so', async () => {
  const { lifecycle, events } = harness({ quit: async () => ({ drained: false }) });
  await lifecycle.userQuit();
  assert.match(
    events.find((e) => e.startsWith('notify:')),
    /DRAIN_NOT_CONFIRMED/,
  );
});

test('Stop safely with nothing running says so instead of reopening the window', async () => {
  const { lifecycle, events } = harness();
  await lifecycle.stopSafely();
  assert.equal(events.length, 2);
  assert.equal(events[0], 'contribution:false');
  assert.match(events[1], /^notify:.*Nothing is running.*Không có/);
});

test('Stop safely confirms when it really stopped something', async () => {
  const { lifecycle, events } = harness({ bridge: {} });
  await lifecycle.stopSafely();
  assert.match(events.at(-1), /^notify:.*Contribution is OFF.*đang tắt/);
});

test('Stop safely failures are shown with their code', async () => {
  const { lifecycle, events } = harness({
    contribution: async () => {
      throw Error('AGENT_TIMEOUT');
    },
  });
  await lifecycle.stopSafely();
  assert.match(
    events.find((e) => e.startsWith('notify:')),
    /AGENT_TIMEOUT/,
  );
});

test('a startup failure is logged, shown to the user and then the app exits', async () => {
  const { lifecycle, events } = harness();
  await lifecycle.startupFailed(Error('SECURE_STORAGE_REQUIRED'));
  assert.ok(events.some((e) => e.startsWith('log:startup failed')));
  assert.match(
    events.find((e) => e.startsWith('fail:')),
    /SECURE_STORAGE_REQUIRED/,
  );
  assert.equal(events.at(-1), 'quitApp');
  assert.equal(lifecycle.exiting, true);
});

test('every code the app can raise has a bilingual explanation, and unknown codes still show the code', () => {
  for (const code of [
    'SETUP_IN_PROGRESS',
    'DRAIN_NOT_CONFIRMED',
    'ACTION_IN_PROGRESS',
    'AGENT_TIMEOUT',
    'AGENT_UNAVAILABLE',
  ])
    assert.match(describeCode(code), / \/ /, code);
  assert.match(describeCode('SOMETHING_NEW'), /SOMETHING_NEW/);
  assert.match(describeCode('not a code, contains token=abc123'), /ACTION_FAILED/);
  assert.ok(!describeCode('not a code, contains token=abc123').includes('abc123'));
});

test('the log keeps recent lines, redacts secrets, rotates and never throws', async (t) => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'worker-log-'));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  const log = createLog(path.join(dir, 'logs'), { maxBytes: 2000 });
  log.info('command', {
    action: 'login',
    ms: 12,
    password: 'hunter2',
    deviceToken: 'tok',
    nested: { a: 1 },
    text: 'x'.repeat(500),
  });
  log.error('boom', Error('LAB_UNREACHABLE'));
  log.info('two\nlines\r\nforged INFO fake entry');
  const text = log.tail(10);
  assert.match(text, /command/);
  assert.match(text, /LAB_UNREACHABLE/);
  assert.ok(!/hunter2|"tok"|tok\b/.test(text.replace('deviceToken', '')), text);
  assert.ok(text.length < 2500);
  assert.match(text, /nested=\[object\]/);
  assert.equal(text.split('\n').length, 3, 'a message cannot forge extra log lines');
  for (let i = 0; i < 60; i++) log.info('filler ' + i);
  const files = await fs.readdir(path.join(dir, 'logs'));
  assert.deepEqual(files.sort(), ['worker.log', 'worker.log.1']);
  assert.ok((await fs.stat(path.join(dir, 'logs', 'worker.log'))).size <= 2000 + 400);
  assert.match(log.tail(3), /filler 59/);
  await fs.writeFile(path.join(dir, 'plain-file'), 'x');
  const broken = createLog(path.join(dir, 'plain-file', 'logs'));
  broken.info('still fine');
  assert.equal(broken.tail(5), '');
});

test('an unclassified action failure keeps its stack in the log; a known code does not need one', async (t) => {
  // The first Windows candidate6 self-test failed with ACTION_FAILED and left nothing to diagnose (ADR-009, F12).
  const { recordActionFailure } = require('../electron/lifecycle.cjs');
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'worker-log-'));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  const log = createLog(path.join(dir, 'logs'));
  const error = new TypeError(
    'cannot read the reference at C:\\Users\\someone with token=abcdefabcdefabcdefabcdefabcdefabcdef',
  );
  assert.equal(recordActionFailure(log, 'selftest', error, 23800), 'ACTION_FAILED');
  const text = log.tail();
  assert.match(text, /action=selftest ok=false code=ACTION_FAILED ms=23800/);
  assert.match(text, /DETAIL action selftest failed: TypeError/);
  assert.match(text, /at /); // a stack frame
  assert.ok(!text.includes('abcdefabcdefabcdefabcdefabcdefabcdef'));
  assert.equal(recordActionFailure(log, 'pair', Error('PAIRING_CODE_EXPIRED'), 5), 'PAIRING_CODE_EXPIRED');
  assert.equal(log.tail().match(/DETAIL/g).length, 1);
});
