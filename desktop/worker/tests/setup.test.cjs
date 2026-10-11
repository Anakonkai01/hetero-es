const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const tar = require('tar');
const { extract, run } = require('../electron/setup.cjs');
test('archive rejects links outside runtime; safe relative symlinks are retained', async (t) => { const root = await fs.mkdtemp(path.join(os.tmpdir(), 'worker-extract-')); t.after(() => fs.rm(root, { recursive: true, force: true })); const src = path.join(root, 'src'); await fs.mkdir(path.join(src, 'python', 'bin'), { recursive: true }); await fs.writeFile(path.join(src, 'python', 'bin', 'python3.12'), 'test'); await fs.symlink('python3.12', path.join(src, 'python', 'bin', 'python3')); const file = path.join(root, 'safe.tar.gz'); await tar.c({ cwd: src, file, gzip: true }, ['python']); await extract(file, path.join(root, 'safe')); assert.equal(await fs.readFile(path.join(root, 'safe', 'python', 'bin', 'python3'), 'utf8'), 'test'); await fs.symlink('../../../outside', path.join(src, 'python', 'bin', 'bad')); await tar.c({ cwd: src, file: path.join(root, 'bad.tar.gz'), gzip: true }, ['python']); await assert.rejects(extract(path.join(root, 'bad.tar.gz'), path.join(root, 'bad')), /UNSAFE/); });
test('runtime subprocess timeout is bounded and errors omit paths and stderr', async () => { await assert.rejects(run(process.execPath, ['-e', 'setTimeout(()=>{},10000)'], { timeout: 30 }), /RUNTIME_PROCESS_TIMEOUT/); await assert.rejects(run(process.execPath, ['-e', 'process.stderr.write("private token");process.exit(2)']), /^Error: RUNTIME_PROCESS_FAILED$/); });
