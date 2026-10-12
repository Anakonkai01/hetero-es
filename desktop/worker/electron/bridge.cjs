const { spawn } = require('node:child_process');
const crypto = require('node:crypto');
class Bridge {
    constructor(python, source, config, token) { this.child = spawn(python, ['-m', 'heteroes.product.desktop_bridge'], { windowsHide: true, env: { ...process.env, PYTHONPATH: source, PYTHONNOUSERSITE: '1', PYTHONUTF8: '1' }, stdio: ['pipe', 'pipe', 'pipe'] }); this.pending = new Map(); let buffer = ''; this.child.stdout.on('data', data => { buffer += data; let newline; while ((newline = buffer.indexOf('\n')) >= 0) {
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
        }
        catch { }
    } }); this.child.stderr.on('data', () => { }); const failed = () => { for (const request of this.pending.values()) {
        clearTimeout(request.timeout);
        request.reject(Error('AGENT_UNAVAILABLE'));
    } this.pending.clear(); }; this.child.stdin.on('error', failed); this.child.on('error', failed); this.child.on('exit', failed); this.ready = this.call('init', { config, deviceToken: token }); }
    call(action, extra = {}) { if (!['init', 'status', 'off', 'quit', 'check_connection'].includes(action))
        return Promise.reject(Error('INVALID_BRIDGE_ACTION')); return new Promise((resolve, reject) => { const id = crypto.randomUUID(); const timeout = setTimeout(() => { this.pending.delete(id); reject(Error('AGENT_TIMEOUT')); }, 30000); this.pending.set(id, { resolve, reject, timeout }); this.child.stdin.write(JSON.stringify({ id, action, ...extra }) + '\n', error => { if (error) {
        clearTimeout(timeout);
        this.pending.delete(id);
        reject(Error('AGENT_UNAVAILABLE'));
    } }); }); }
}
module.exports = { Bridge };
