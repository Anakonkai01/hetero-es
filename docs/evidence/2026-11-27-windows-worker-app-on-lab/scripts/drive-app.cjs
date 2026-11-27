// Drive the installed Worker app like its page does: window.worker.call(action) over the DevTools protocol.
// Run with the app's own exe: ELECTRON_RUN_AS_NODE=1 "HeteroES Worker.exe" drive-app.cjs <port> <log> <action...>
const fs = require('node:fs');
const [port, logFile, ...actions] = process.argv.slice(2);
const log = (row) => fs.appendFileSync(logFile, JSON.stringify({ t: new Date().toISOString(), ...row }) + '\n');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function connect() {
  for (let i = 0; i < 60; i++) {
    try {
      const targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
      const page = targets.find((t) => t.type === 'page');
      if (page) return page.webSocketDebuggerUrl;
    } catch {}
    await sleep(1000);
  }
  throw Error('no page target');
}
(async () => {
  const ws = new WebSocket(await connect());
  await new Promise((r, j) => ((ws.onopen = r), (ws.onerror = j)));
  let id = 0;
  const pending = new Map();
  ws.onmessage = (m) => {
    const d = JSON.parse(m.data);
    if (pending.has(d.id)) pending.get(d.id)(d), pending.delete(d.id);
  };
  const evaluate = (expression) =>
    new Promise((resolve) => {
      const n = ++id;
      pending.set(n, resolve);
      ws.send(JSON.stringify({ id: n, method: 'Runtime.evaluate', params: { expression, awaitPromise: true, returnByValue: true } }));
    }).then((d) => (d.result?.exceptionDetails ? { evalError: d.result.exceptionDetails.text } : d.result?.result?.value));
  for (let i = 0; i < 30 && !(await evaluate('typeof window.worker')).startsWith('object'); i++) await sleep(1000);
  const first = await evaluate("window.worker.call('status')");
  const folder = first?.result?.setup?.dataFolder ?? '';
  log({ dataFolder: folder });
  if (!/^D:\\/i.test(folder)) throw Error('data folder is not on D: ' + folder); // the owner's C: is nearly full
  for (const action of actions) {
    log({ action, phase: 'start', status: await evaluate("window.worker.call('status')") });
    await evaluate(`window.__done = undefined; window.worker.call(${JSON.stringify(action)}).then((r) => (window.__done = r), (e) => (window.__done = { ok: false, error: String(e) })); 1`);
    let last = '';
    for (;;) {
      await sleep(15000);
      const done = await evaluate('window.__done');
      const status = await evaluate("window.worker.call('status')");
      const progress = JSON.stringify(status?.result?.setup?.progress ?? status?.result?.selfTest ?? '');
      if (progress !== last) log({ action, progress: JSON.parse(progress || '""') }), (last = progress);
      if (done !== undefined && done !== null) {
        log({ action, phase: 'done', result: done, status });
        if (!done.ok) process.exit(2);
        break;
      }
    }
  }
  process.exit(0);
})().catch((e) => (log({ fatal: String(e) }), process.exit(1)));
