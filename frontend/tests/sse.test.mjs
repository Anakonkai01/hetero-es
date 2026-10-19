import { test } from 'node:test';
import assert from 'node:assert/strict';
import { SseParser } from '../src/lib/sse.ts';

test('whole messages are parsed with their event name and JSON data', () => {
  const parser = new SseParser();
  assert.deepEqual(parser.push('event: timeline\ndata: {"a":1}\n\nevent: end\ndata: {}\n\n'), [
    { event: 'timeline', data: '{"a":1}' },
    { event: 'end', data: '{}' },
  ]);
});

test('a message split across chunks (even in the middle of a line) is emitted once, when complete', () => {
  const parser = new SseParser();
  assert.deepEqual(parser.push('event: time'), []);
  assert.deepEqual(parser.push('line\ndata: {"a"'), []);
  assert.deepEqual(parser.push(':1}\n'), []);
  assert.deepEqual(parser.push('\n'), [{ event: 'timeline', data: '{"a":1}' }]);
  assert.deepEqual(parser.push(''), []);
});

test('heartbeat comments are reported separately and never mistaken for data', () => {
  const parser = new SseParser();
  assert.deepEqual(parser.push(': heartbeat\n\n'), [{ event: 'comment', data: '' }]);
  assert.deepEqual(parser.push(': one\n\nevent: x\ndata: 1\n\n'), [
    { event: 'comment', data: '' },
    { event: 'x', data: '1' },
  ]);
});

test('windows line endings, multi-line data and a missing event name are handled', () => {
  const parser = new SseParser();
  assert.deepEqual(parser.push('event: a\r\ndata: 1\r\n\r\n'), [{ event: 'a', data: '1' }]);
  assert.deepEqual(parser.push('data: one\ndata: two\n\n'), [{ event: 'message', data: 'one\ntwo' }]);
});

test('a runaway message is dropped instead of growing without bound', () => {
  const parser = new SseParser(100);
  assert.deepEqual(parser.push('data: ' + 'x'.repeat(500)), []);
  assert.deepEqual(
    parser.push('\n\nevent: ok\ndata: 1\n\n'),
    [{ event: 'ok', data: '1' }],
    'parsing recovers at the next message',
  );
});
