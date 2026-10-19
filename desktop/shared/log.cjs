const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const SECRET = /token|password|secret|authorization|cookie|key/i;
const MAX_DETAIL_LINES = 20;
const clip = (value, limit = 200) => String(value).replace(/[\r\n]+/g, ' ').slice(0, limit);
// Small append-only diagnostics log. It records what happened (action, code, duration), never request bodies,
// and it must never be the reason the app fails: every filesystem error is swallowed.
function createLog(dir, { maxBytes = 256 * 1024, now = () => new Date(), home = os.homedir() } = {}) {
    const file = path.join(dir, 'worker.log');
    const escape = text => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const homePattern = home ? new RegExp(escape(home).replace(/\\\\/g, '[\\\\/]'), 'gi') : null;
    // Free text from a child process: keep the end, drop the user's profile path and anything shaped like a token.
    const sanitise = text => {
        const clean = String(text).replace(homePattern ?? /$^/g, '~').replace(/Bearer\s+\S+/gi, 'Bearer [redacted]').replace(/[A-Za-z0-9+/_=-]{32,}/g, '[redacted]');
        return clean.split(/\r?\n/).filter(Boolean).slice(-MAX_DETAIL_LINES).map(line => '  ' + line.slice(0, 300));
    };
    function write(level, message, fields = {}) {
        try {
            const parts = Object.entries(fields).map(([key, value]) => `${clip(key, 40)}=${SECRET.test(key) ? '[redacted]' : typeof value === 'object' && value !== null ? '[object]' : clip(value)}`);
            const line = `${now().toISOString()} ${level} ${clip(message, 300)}${parts.length ? ' ' + parts.join(' ') : ''}\n`;
            fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
            if (fs.existsSync(file) && fs.statSync(file).size + line.length > maxBytes) fs.renameSync(file, file + '.1');
            fs.appendFileSync(file, line, { mode: 0o600 });
        } catch { /* logging must not break the app */ }
    }
    function detail(message, text) {
        try {
            const lines = [`${now().toISOString()} DETAIL ${clip(message, 300)}`, ...sanitise(text)];
            const block = lines.join('\n') + '\n';
            fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
            if (fs.existsSync(file) && fs.statSync(file).size + block.length > maxBytes) fs.renameSync(file, file + '.1');
            fs.appendFileSync(file, block, { mode: 0o600 });
        } catch { /* logging must not break the app */ }
    }
    return {
        detail,
        info: (message, fields) => write('INFO', message, fields),
        error: (message, error) => write('ERROR', message, { code: /^[A-Z][A-Z0-9_]+$/.test(error?.message ?? '') ? error.message : 'ACTION_FAILED', name: error?.name ?? '' }),
        tail(lines = 200) {
            try { return fs.readFileSync(file, 'utf8').split('\n').filter(Boolean).slice(-lines).join('\n'); } catch { return ''; }
        },
    };
}
module.exports = { createLog };
