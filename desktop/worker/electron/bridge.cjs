const { spawn } = require('node:child_process');
const crypto = require('node:crypto');
const TAIL_BYTES = 4096;
// Windows reports a missing system library as a status code, not as text: 0xC0000135 is "DLL not found", 0xC000007B "bad image".
const MISSING_LIBRARY_EXIT = new Set([0xc0000135, 0xc000007b]);
const MISSING_LIBRARY_TEXT = /DLL load failed|WinError 126|MSVCP140|VCRUNTIME140/;
// The one code the owner sees for a child that ended on its own. The raw stderr stays in the local log only.
function classifyExit({ exitCode, stderrTail = '' }) {
  return MISSING_LIBRARY_EXIT.has(exitCode) || MISSING_LIBRARY_TEXT.test(stderrTail)
    ? 'WINDOWS_RUNTIME_MISSING'
    : 'AGENT_EXITED';
}
class Bridge {
  constructor(python, source, config, token) {
    this.stderrTail = '';
    this.spawnCode = '';
    this.exitInfo = null;
    this.pending = new Map();
    this.child = spawn(python, ['-m', 'heteroes.product.desktop_bridge'], {
      windowsHide: true,
      env: { ...process.env, PYTHONPATH: source, PYTHONNOUSERSITE: '1', PYTHONUTF8: '1' },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    let buffer = '';
    this.child.stdout.on('data', (data) => {
      buffer += data;
      let newline;
      while ((newline = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, newline);
        buffer = buffer.slice(newline + 1);
        try {
          const row = JSON.parse(line);
          const request = this.pending.get(row.id);
          if (request) {
            clearTimeout(request.timeout);
            this.pending.delete(row.id);
            row.error ? request.reject(Error('AGENT_' + row.error)) : request.resolve(row.result);
          }
        } catch {}
      }
    });
    this.child.stderr.on('data', (data) => {
      this.stderrTail = (this.stderrTail + data).slice(-TAIL_BYTES);
    });
    // A broken pipe usually means the child is ending; give its exit status a moment to arrive so the code is specific.
    this.child.stdin.on('error', () => this.settleSoon());
    this.child.on('error', (error) => {
      this.spawnCode = error.code ?? 'UNKNOWN';
      this.settle();
    });
    this.child.on('exit', (exitCode, signal) => {
      this.exitInfo = { exitCode, signal };
      this.settleSoon();
    });
    this.child.on('close', () => this.settle());
    this.ready = this.call('init', { config, deviceToken: token });
  }
  exited() {
    return Boolean(this.spawnCode || this.exitInfo);
  }
  failureCode() {
    if (this.spawnCode) return 'AGENT_SPAWN_FAILED';
    return this.exitInfo ? classifyExit({ ...this.exitInfo, stderrTail: this.stderrTail }) : 'AGENT_UNAVAILABLE';
  }
  // What is known about why the child is gone. Only the code reaches the owner; the rest is for the local log.
  failure() {
    return {
      code: this.failureCode(),
      exitCode: this.exitInfo?.exitCode ?? null,
      signal: this.exitInfo?.signal ?? null,
      spawnCode: this.spawnCode,
      stderrTail: this.stderrTail,
    };
  }
  settle() {
    clearTimeout(this.settleTimer);
    const code = this.failureCode();
    for (const request of this.pending.values()) {
      clearTimeout(request.timeout);
      request.reject(Error(code));
    }
    this.pending.clear();
  }
  settleSoon() {
    clearTimeout(this.settleTimer);
    this.settleTimer = setTimeout(() => this.settle(), 300);
  }
  call(action, extra = {}) {
    if (!['init', 'status', 'off', 'quit', 'check_connection'].includes(action))
      return Promise.reject(Error('INVALID_BRIDGE_ACTION'));
    if (this.exited()) return Promise.reject(Error(this.failureCode()));
    return new Promise((resolve, reject) => {
      const id = crypto.randomUUID();
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        reject(Error('AGENT_TIMEOUT'));
      }, 30000);
      this.pending.set(id, { resolve, reject, timeout });
      this.child.stdin.write(JSON.stringify({ id, action, ...extra }) + '\n', (error) => {
        if (error) this.settleSoon();
      });
    });
  }
}
module.exports = { Bridge, classifyExit };
