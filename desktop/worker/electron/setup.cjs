const fs = require('node:fs');
const fsp = fs.promises;
const path = require('node:path');
const crypto = require('node:crypto');
const tar = require('tar');
const { spawn, execFileSync } = require('node:child_process');
const { verifiedDownload, digest } = require('./download.cjs');
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
class Setup {
    constructor(root, resources, onProgress = () => { }) {
        this.root = root; this.resources = resources; this.onProgress = onProgress;
        this.progress = { stage: 'NOT_INSTALLED' }; this.running = false;
        const storageFile = path.join(root, 'storage.json');
        this.storage = fs.existsSync(storageFile) ? JSON.parse(fs.readFileSync(storageFile, 'utf8')) : {};
        if (Object.keys(this.storage).some(key => !['downloads', 'models', 'artifacts', 'volumeUUID'].includes(key)))
            throw Error('INVALID_STORAGE_DIRECTORY');
        if (this.storage.volumeUUID !== undefined &&
            (process.platform !== 'linux' || typeof this.storage.volumeUUID !== 'string' || !/^[a-fA-F0-9-]+$/.test(this.storage.volumeUUID)))
            throw Error('INVALID_STORAGE_VOLUME');
        for (const value of [this.storage.downloads, this.storage.models, this.storage.artifacts].filter(value => value !== undefined)) {
            if (typeof value !== 'string' || !path.isAbsolute(value) || value === '/mnt/sekai' || value.startsWith('/mnt/sekai/'))
                throw Error('INVALID_STORAGE_DIRECTORY');
        }
    }
    checkStorage() {
        if (!this.storage.volumeUUID) return;
        try {
            const expected = fs.realpathSync('/dev/disk/by-uuid/' + this.storage.volumeUUID);
            for (const directory of [this.storage.downloads, this.storage.models, this.storage.artifacts].filter(Boolean)) {
                let ancestor = directory;
                while (!fs.existsSync(ancestor)) ancestor = path.dirname(ancestor);
                const source = execFileSync('findmnt', ['-rn', '-T', ancestor, '-o', 'SOURCE'], { encoding: 'utf8', timeout: 5000 }).trim();
                if (fs.realpathSync(source) !== expected) throw Error('STORAGE_VOLUME_UNAVAILABLE');
            }
        } catch { throw Error('STORAGE_VOLUME_UNAVAILABLE'); }
    }
    profile() { const profile = JSON.parse(fs.readFileSync(path.join(this.resources, 'profile.json'), 'utf8')); const platform = process.platform === 'win32' ? 'windows' : 'linux'; if (!['win32', 'linux'].includes(process.platform))
        throw Error('PLATFORM_UNSUPPORTED'); return { ...profile, platform, selected: profile.platforms[platform] }; }
    paths() { const profile = this.profile(); const hash = crypto.createHash('sha256').update(JSON.stringify(profile)).digest('hex').slice(0, 12); const root = path.join(this.root, 'runtimes', hash); return { root, python: path.join(root, 'python', process.platform === 'win32' ? 'python.exe' : 'bin/python3.12'), model: path.join(this.storage.models ?? path.join(root, 'models'), profile.modelRevision), downloads: this.storage.downloads ?? path.join(this.root, 'downloads'), source: path.join(root, 'src'), scripts: path.join(root, 'scripts'), complete: path.join(root, 'READY.json') }; }
    status() { try {
        this.checkStorage();
        const p = this.paths();
        return { installed: fs.existsSync(p.complete) && fs.existsSync(p.python) && fs.existsSync(path.join(p.scripts, 'run_worker.py')) && this.profile().modelFiles.every(item => { const file = path.join(p.model, item.name); return fs.existsSync(file) && fs.statSync(file).size === item.sizeBytes; }), running: this.running, progress: this.progress };
    }
    catch {
        return { installed: false, running: this.running, progress: this.progress, profileAvailable: false };
    } }
    async install() {
        if (this.running)
            throw Error('SETUP_IN_PROGRESS');
        this.running = true;
        const update = value => { this.progress = value; this.onProgress(value); };
        try {
            this.checkStorage();
            const profile = this.profile(), p = this.paths();
            if (this.status().installed)
                return this.status();
            await fsp.mkdir(p.root, { recursive: true, mode: 0o700 });
            const runtimeBytes = [profile.selected.python, ...profile.selected.wheels].reduce((sum, item) => sum + item.sizeBytes, 0);
            const modelBytes = profile.modelFiles.reduce((sum, item) => sum + item.sizeBytes, 0);
            const volumes = new Map();
            for (const [directory, required] of [[p.root, runtimeBytes * 2 + 512 * 1024 * 1024], [p.downloads, runtimeBytes], [p.model, modelBytes]]) {
                await fsp.mkdir(directory, { recursive: true, mode: 0o700 });
                const { dev } = await fsp.stat(directory), space = await fsp.statfs(directory);
                const previous = volumes.get(dev) ?? { required: 0, free: Number(space.bavail) * Number(space.bsize) };
                previous.required += required; volumes.set(dev, previous);
            }
            if ([...volumes.values()].some(volume => volume.free < volume.required))
                throw Error('INSUFFICIENT_DISK_SPACE');
            const cache = p.downloads;
            update({ stage: 'PYTHON' });
            const archive = await verifiedDownload(profile.selected.python, cache, v => update({ stage: 'PYTHON', ...v }));
            await extract(archive, p.root);
            const runtime = path.join(this.resources, 'runtime.tar.gz');
            if (await digest(runtime) !== profile.runtimeSha256)
                throw Error('RUNTIME_CHECKSUM_MISMATCH');
            await extract(runtime, p.root);
            const wheelhouse = path.join(cache, profile.platform);
            for (const wheel of profile.selected.wheels)
            {
                this.checkStorage();
                await verifiedDownload(wheel, wheelhouse, v => update({ stage: 'DEPENDENCIES', ...v }));
            }
            update({ stage: 'INSTALLING' });
            await run(p.python, ['-m', 'pip', 'install', '--no-index', '--find-links', wheelhouse, '--require-hashes', '-r', path.join(this.resources, profile.selected.lockFile)], { env: { ...process.env, PYTHONNOUSERSITE: '1', PYTHONUTF8: '1' } });
            for (const model of profile.modelFiles)
            {
                this.checkStorage();
                await verifiedDownload(model, p.model, v => update({ stage: 'MODEL', ...v }));
            }
            await fsp.writeFile(p.complete, JSON.stringify({ profile: 'desktop-v1', platform: profile.platform, verifiedAt: new Date().toISOString() }), { mode: 0o600 });
            update({ stage: 'READY' });
            return this.status();
        }
        catch (error) {
            update({ stage: 'ERROR', code: error.message });
            throw error;
        }
        finally {
            this.running = false;
        }
    }
    async selfTest() {
        if (!this.status().installed)
            throw Error('RUNTIME_NOT_INSTALLED');
        if (this.running)
            throw Error('SETUP_IN_PROGRESS');
        this.running = true;
        const p = this.paths();
        let buffer = '', result, error;
        try {
            await run(p.python, ['-m', 'heteroes.product.qualification'], { cwd: p.root, env: { ...process.env, PYTHONPATH: p.source, PYTHONNOUSERSITE: '1', PYTHONUTF8: '1' }, input: { modelPath: p.model, referencePath: path.join(this.resources, 'reference.json') }, onLine: chunk => { buffer += chunk; const lines = buffer.split('\n'); buffer = lines.pop(); for (const line of lines) {
                    try {
                        const row = JSON.parse(line);
                        if (row.progress) {
                            this.progress = { stage: 'SELF_TEST', ...row.progress };
                            this.onProgress(this.progress);
                        }
                        if (row.result)
                            result = row.result;
                        if (row.error)
                            error = row.code;
                    }
                    catch { }
                } } });
            if (!result || error)
                throw Error(error || 'COMPATIBILITY_FAILED');
            return result;
        }
        catch (failure) {
            const code = error || failure.message;
            this.progress = { stage: 'ERROR', code };
            this.onProgress(this.progress);
            throw Error(code);
        }
        finally {
            this.running = false;
        }
    }
}
module.exports = { Setup, run, extract };
