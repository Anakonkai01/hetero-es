import { test } from 'node:test';
import assert from 'node:assert/strict';
import { friendlyFileName } from '../src/lib/files.ts';

test('hash-named checkpoint files are shortened, readable names are not', () => {
    const hash = '953429cbc448caf52844f364dd7889d24cde729032bf1e8714755a68d7b041ac';
    assert.equal(friendlyFileName(hash + '.bin'), '953429cb…41ac.bin');
    assert.equal(friendlyFileName(hash), '953429cb…41ac');
    assert.equal(friendlyFileName('config.json'), 'config.json');
    assert.equal(friendlyFileName('summary-1791620995451577606.json'), 'summary-1791620995451577606.json');
    assert.equal(friendlyFileName('abcdef.bin'), 'abcdef.bin');
});
