import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fileStem } from '../src/lib/chartExport.ts';

test('file names are safe, ASCII and never empty', () => {
  assert.equal(fileStem('M2 three GPU agent acceptance v2'), 'M2-three-GPU-agent-acceptance-v2');
  assert.equal(fileStem('Thí nghiệm đầu tiên'), 'Thi-nghiem-dau-tien');
  assert.equal(
    fileStem('v1.2 final'),
    'v1-2-final',
    'dots never appear, so a name cannot become a hidden file or an extension trick',
  );
  assert.equal(fileStem('../../etc/passwd'), 'etc-passwd');
  assert.equal(fileStem('   '), 'run');
  assert.equal(fileStem('***'), 'run');
  assert.ok(fileStem('x'.repeat(200)).length <= 60);
});
