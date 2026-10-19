const fs = require('node:fs');
const fsp = fs.promises;
const path = require('node:path');
const tar = require('tar');
const {spawn} = require('node:child_process');
function run(program, args, options = {}) { return new Promise((resolve, reject) => { const child = spawn(program, args, { windowsHide: true, ...options, stdio: ['pipe', 'pipe', 'pipe'] }); let output = '', problem = ''; const timer = setTimeout(() => { child.kill(); reject(Error('RUNTIME_PROCESS_TIMEOUT')); }, options.timeout ?? 600000); child.stdin.on('error', () => { }); child.on('close', () => clearTimeout(timer)); child.stdout.on('data', b => { output = (output + b).slice(-65536); options.onLine?.(b.toString()); }); child.stderr.on('data', b => { const message = b.toString(); if (/DLL load failed|WinError 126|MSVCP140|VCRUNTIME140/.test(message))
    problem = 'WINDOWS_RUNTIME_MISSING'; }); child.on('error', () => reject(Error('RUNTIME_PROCESS_FAILED'))); child.on('exit', code => code === 0 ? resolve(output) : reject(Error(problem || 'RUNTIME_PROCESS_FAILED'))); if (options.input)
    child.stdin.end(JSON.stringify(options.input));
else
    child.stdin.end(); }); }
async function extract(file, dir) {
    let invalid = false;
    await tar.t({ file, strict: true, onReadEntry: entry => {
            const name = entry.path.replaceAll('\\', '/');
            if (path.posix.isAbsolute(name) || /^[A-Za-z]:/.test(name) || name.split('/').includes('..'))
                invalid = true;
            if (entry.linkpath) {
                const link = entry.linkpath.replaceAll('\\', '/');
                const linked = path.posix.normalize(path.posix.join(entry.type === 'SymbolicLink' ? path.posix.dirname(name) : '', link));
                if (path.posix.isAbsolute(link) || /^[A-Za-z]:/.test(link) || linked === '..' || linked.startsWith('../'))
                    invalid = true;
            }
        } });
    if (invalid)
        throw Error('UNSAFE_ARCHIVE');
    await fsp.mkdir(dir, { recursive: true });
    await tar.x({ file, cwd: dir, strict: true, preservePaths: false });
}

module.exports = {run, extract};
