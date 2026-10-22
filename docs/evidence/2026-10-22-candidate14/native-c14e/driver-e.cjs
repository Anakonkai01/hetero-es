// Native Windows packaged Worker control; Node/WebSocket only, secrets stay in private files.
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');
const task = __dirname;
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function endpoint(port) {
  for (let i = 0; i < 120; i++) {
    try {
      const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      const target = targets.find((t) => t.type === 'page') ?? targets[0];
      if (target?.webSocketDebuggerUrl) return target.webSocketDebuggerUrl;
    } catch {}
    await wait(250);
  }
  throw Error('DEBUG_ENDPOINT_NOT_READY');
}
async function connect(port) {
  const socket = new WebSocket(await endpoint(port));
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  let serial = 0;
  const pending = new Map();
  socket.onmessage = ({ data }) => {
    const reply = JSON.parse(data);
    const action = pending.get(reply.id);
    if (!action) return;
    pending.delete(reply.id);
    if (reply.error) action.reject(Error(reply.error.message)); else action.resolve(reply.result);
  };
  return {
    close: () => socket.close(),
    call: (method, params = {}) => new Promise((resolve, reject) => {
      const id = ++serial;
      pending.set(id, { resolve, reject });
      socket.send(JSON.stringify({ id, method, params }));
    }),
  };
}
async function evaluate(client, expression) {
  const reply = await client.call('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (reply.exceptionDetails) throw Error(reply.exceptionDetails.exception?.description ?? 'EVALUATE_FAILED');
  return reply.result.value;
}
(async () => {
  const [action, argsFile] = process.argv.slice(2);
  if (action === 'launch') {
    const env = { ...process.env, HETEROES_GPU_ACCEPTANCE: '1' };
    delete env.ELECTRON_RUN_AS_NODE;
    const executable = path.join(process.env.LOCALAPPDATA, 'Programs', '@heteroesworker', 'HeteroES Worker.exe');
    const child = spawn(executable, ['--remote-debugging-port=19323', '--inspect=19324', '--disable-gpu'], {
      env, detached: true, stdio: 'ignore',
    });
    child.unref();
    fs.writeFileSync(path.join(task, 'app-pid.json'), JSON.stringify({ pid: child.pid }));
  }
  const main = await connect(19324);
  const ready = "typeof process !== 'undefined' && !!process.mainModule";
  for (let i = 0; i < 120 && !(await evaluate(main, ready).catch(() => false)); i++) await wait(250);
  const userData = await evaluate(main, "process.mainModule.require('electron').app.getPath('userData')");
  const expected = path.join(process.env.APPDATA, '@heteroes', 'worker');
  if (path.normalize(userData).toLowerCase() !== path.normalize(expected).toLowerCase()) throw Error('UNEXPECTED_USER_DATA');
  main.close();
  const renderer = await connect(19323);
  const ui = `(() => { const b = document.querySelector('button.switch'); const h = document.querySelector('.station-headline');
    return { switchFound: !!b, disabled: b ? b.disabled : null, checked: b ? b.getAttribute('aria-checked') : null,
      label: b ? b.getAttribute('aria-label') : null, headline: h ? h.textContent : null,
      detail: (document.querySelector('.station-headline + p') || {}).textContent || null }; })()`;
  const summary = async () => {
    const r = await evaluate(renderer, "window.worker.call('status', {})");
    const s = r.value ?? r.data ?? r.result ?? r;
    return { ok: r.ok, signedIn: s.signedIn, approvalStatus: s.device?.approvalStatus, build: s.build,
      agentEnabled: s.agent?.enabled ?? null, drained: s.agent?.drained ?? null, connection: s.connection,
      telemetryKeys: s.telemetry ? Object.keys(s.telemetry) : null };
  };
  if (['ui', 'click', 'shot'].includes(action)) {
    const out = { action, at: new Date().toISOString() };
    out.before = { status: await summary(), ui: await evaluate(renderer, ui) };
    if (action === 'click') {
      if (!out.before.ui.switchFound || out.before.ui.disabled) throw Error('SWITCH_NOT_CLICKABLE');
      await evaluate(renderer, "document.querySelector('button.switch').click(), true");
      for (let i = 0; i < 240; i++) {
        await wait(500);
        const now = await evaluate(renderer, ui);
        if (now.checked !== out.before.ui.checked && !now.disabled) break;
      }
      out.after = { status: await summary(), ui: await evaluate(renderer, ui) };
    }
    if (action === 'shot') {
      const shot = await renderer.call('Page.captureScreenshot', { format: 'png' });
      fs.writeFileSync(path.join(task, (argsFile || 'shot') + '.png'), Buffer.from(shot.data, 'base64'));
    }
    fs.writeFileSync(path.join(task, action + '-ui-result.json'), JSON.stringify(out, null, 2));
    renderer.close(); console.log(JSON.stringify(out)); return;
  }
  let args = argsFile && !argsFile.startsWith('--') ? JSON.parse(fs.readFileSync(argsFile, 'utf8')) : {};
  let requested = action === 'launch' ? 'status' : action;
  if (requested === 'selftest' && !process.argv.includes('--gpu')) throw Error('EXPLICIT_GPU_FLAG_REQUIRED');
  if (requested === 'quit') {
    await renderer.call('Runtime.evaluate', { expression: "window.worker.call('quit', {})", awaitPromise: false });
    renderer.close(); console.log('Quit requested; verify process exit separately.'); return;
  }
  const reply = await evaluate(renderer, `window.worker.call(${JSON.stringify(requested)}, ${JSON.stringify(args)})`);
  fs.writeFileSync(path.join(task, `${action}-result.json`), JSON.stringify(reply, null, 2));
  renderer.close();
  if (!reply.ok) throw Error(reply.error);
  console.log(action + ': OK');
})().catch((error) => { fs.writeFileSync(path.join(task, 'driver-error.json'), JSON.stringify({ error: String(error.message) })); console.error(String(error.message)); process.exit(1); });
