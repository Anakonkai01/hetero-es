const fs = require('node:fs');
const path = require('node:path');
const SECRET = /token|password|secret|authorization|cookie|key/i;
const clip = (value, limit = 200) => String(value).replace(/[\r\n]+/g, ' ').slice(0, limit);
// Small append-only diagnostics log. It records what happened (action, code, duration), never request bodies,
// and it must never be the reason the app fails: every filesystem error is swallowed.
function createLog(dir, { maxBytes = 256 * 1024, now = () => new Date() } = {}) {
    const file = path.join(dir, 'worker.log');
    function write(level, message, fields = {}) {
        try {
            const parts = Object.entries(fields).map(([key, value]) => `${clip(key, 40)}=${SECRET.test(key) ? '[redacted]' : typeof value === 'object' && value !== null ? '[object]' : clip(value)}`);
            const line = `${now().toISOString()} ${level} ${clip(message, 300)}${parts.length ? ' ' + parts.join(' ') : ''}\n`;
            fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
            if (fs.existsSync(file) && fs.statSync(file).size + line.length > maxBytes) fs.renameSync(file, file + '.1');
            fs.appendFileSync(file, line, { mode: 0o600 });
        } catch { /* logging must not break the app */ }
    }
    return {
        info: (message, fields) => write('INFO', message, fields),
        error: (message, error) => write('ERROR', message, { code: /^[A-Z][A-Z0-9_]+$/.test(error?.message ?? '') ? error.message : 'ACTION_FAILED', name: error?.name ?? '' }),
        tail(lines = 200) {
            try { return fs.readFileSync(file, 'utf8').split('\n').filter(Boolean).slice(-lines).join('\n'); } catch { return ''; }
        },
    };
}
module.exports = { createLog };
