// Run quick app actions in order over the DevTools protocol: drive-steps.cjs <port> <log> <steps.json> [credentials.json]
// A step {"action":"login"} takes username/password from credentials.json, which is deleted as soon as it is read;
// they are never logged.
const fs = require('node:fs');
const [port, logFile, stepsFile, credFile] = process.argv.slice(2);
let cred = null;
if (credFile) {
  cred = JSON.parse(fs.readFileSync(credFile, 'utf8'));
  fs.rmSync(credFile, { force: true });
}
const log = (row) => fs.appendFileSync(logFile, JSON.stringify({ t: new Date().toISOString(), ...row }) + '\n');
(async () => {
  const targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
  const ws = new WebSocket(targets.find((t) => t.type === 'page').webSocketDebuggerUrl);
  await new Promise((r, j) => ((ws.onopen = r), (ws.onerror = j)));
  let id = 0;
  const pending = new Map();
  ws.onmessage = (m) => {
    const d = JSON.parse(m.data);
    if (pending.has(d.id)) pending.get(d.id)(d), pending.delete(d.id);
  };
  const call = (action, args) =>
    new Promise((resolve) => {
      const n = ++id;
      pending.set(n, resolve);
      const expression = `window.worker.call(${JSON.stringify(action)}, ${JSON.stringify(args)})`;
      ws.send(JSON.stringify({ id: n, method: 'Runtime.evaluate', params: { expression, awaitPromise: true, returnByValue: true } }));
    }).then((d) => d.result?.result?.value);
  for (const step of JSON.parse(fs.readFileSync(stepsFile, 'utf8'))) {
    const args = step.action === 'login' ? { username: cred.username, password: cred.password } : step.args ?? {};
    const result = await call(step.action, args);
    log({ action: step.action, args: step.action === 'login' ? '<credentials>' : args, result });
    if (!result?.ok) process.exit(2);
  }
  process.exit(0);
})().catch((e) => (log({ fatal: String(e) }), process.exit(1)));
