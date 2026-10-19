/** Check only repository source files, honoring .prettierignore; never inspect ignored private files. */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const files = [
  ...new Set(
    execFileSync('git', ['ls-files', '-z', '--cached', '--others', '--exclude-standard'], {
      cwd: root,
      encoding: 'utf8',
    }).split('\0'),
  ),
].filter((file) => /\.(?:[cm]?js|tsx?|css|json)$/.test(file) && fs.existsSync(path.join(root, file)));
const require = createRequire(import.meta.url);
const metadata = require.resolve('prettier/package.json');
const pkg = JSON.parse(fs.readFileSync(metadata, 'utf8'));
const binary = typeof pkg.bin === 'string' ? pkg.bin : pkg.bin.prettier;
execFileSync(process.execPath, [path.resolve(path.dirname(metadata), binary), '--check', ...files], {
  cwd: root,
  stdio: 'inherit',
});
