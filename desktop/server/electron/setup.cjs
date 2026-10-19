const fs = require('node:fs');
const fsp = fs.promises;
const path = require('node:path');
const crypto = require('node:crypto');
const { extract, run } = require('@heteroes/desktop-shared/runtime.cjs');
const { verifiedDownload, digest } = require('@heteroes/desktop-shared/download.cjs');

class Setup {
  constructor(root, resources, onProgress = () => {}) {
    this.root = root;
    this.resources = resources;
    this.onProgress = onProgress;
    this.progress = { stage: 'NOT_INSTALLED' };
    this.running = false;
  }
  profile() {
    const profile = JSON.parse(fs.readFileSync(path.join(this.resources, 'profile.json'), 'utf8'));
    const platform = process.platform === 'win32' ? 'windows' : 'linux';
    if (!['win32', 'linux'].includes(process.platform)) throw Error('PLATFORM_UNSUPPORTED');
    return { ...profile, platform, selected: profile.platforms[platform] };
  }
  paths() {
    const profile = this.profile();
    const hash = crypto.createHash('sha256').update(JSON.stringify(profile)).digest('hex').slice(0, 12);
    const root = path.join(this.root, 'runtimes', hash);
    return {
      root,
      python: path.join(root, 'python', process.platform === 'win32' ? 'python.exe' : 'bin/python3.12'),
      source: root,
      web: path.join(root, 'web'),
      complete: path.join(root, 'READY.json'),
    };
  }
  status() {
    try {
      const p = this.paths();
      return {
        installed:
          fs.existsSync(p.complete) && fs.existsSync(p.python) && fs.existsSync(path.join(p.web, 'index.html')),
        running: this.running,
        progress: this.progress,
      };
    } catch {
      return { installed: false, running: this.running, progress: this.progress };
    }
  }
  async install() {
    if (this.running) throw Error('SETUP_IN_PROGRESS');
    this.running = true;
    const update = (value) => {
      this.progress = value;
      this.onProgress(value);
    };
    try {
      const profile = this.profile(),
        p = this.paths();
      if (this.status().installed) return this.status();
      await fsp.mkdir(p.root, { recursive: true, mode: 0o700 });
      const space = await fsp.statfs(p.root);
      const bytes = [profile.selected.python, ...profile.selected.wheels].reduce((n, x) => n + x.sizeBytes, 0);
      if (Number(space.bavail) * Number(space.bsize) < bytes * 4 + 256 * 1024 ** 2)
        throw Error('INSUFFICIENT_DISK_SPACE');
      const cache = path.join(this.root, 'downloads');
      update({ stage: 'PYTHON' });
      await extract(
        await verifiedDownload(profile.selected.python, cache, (v) => update({ stage: 'PYTHON', ...v })),
        p.root,
      );
      const bundle = path.join(this.resources, 'runtime.tar.gz');
      if ((await digest(bundle)) !== profile.runtimeSha256) throw Error('RUNTIME_CHECKSUM_MISMATCH');
      await extract(bundle, p.root);
      const wheels = path.join(cache, profile.platform);
      for (const item of profile.selected.wheels)
        await verifiedDownload(item, wheels, (v) => update({ stage: 'DEPENDENCIES', ...v }));
      update({ stage: 'INSTALLING' });
      await run(
        p.python,
        [
          '-m',
          'pip',
          'install',
          '--no-index',
          '--find-links',
          wheels,
          '--require-hashes',
          '-r',
          path.join(this.resources, profile.selected.lockFile),
        ],
        { env: { ...process.env, PYTHONNOUSERSITE: '1', PYTHONUTF8: '1', CUDA_VISIBLE_DEVICES: '' } },
      );
      // Installed dependency compatibility is checked without importing CUDA.
      await run(p.python, ['-m', 'pip', 'check'], { env: { ...process.env, PYTHONNOUSERSITE: '1' } });
      await fsp.writeFile(
        p.complete,
        JSON.stringify({ profile: 'server-cpu-v1', verifiedAt: new Date().toISOString() }),
        { mode: 0o600 },
      );
      update({ stage: 'READY' });
      return this.status();
    } catch (error) {
      update({ stage: 'ERROR', code: error.message });
      throw error;
    } finally {
      this.running = false;
    }
  }
}
module.exports = { Setup, run };
