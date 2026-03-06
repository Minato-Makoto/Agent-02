import assert from 'node:assert/strict';
import test from 'node:test';
import { assertSafeHttpUrl } from '../src/utils/network.ts';
import { resolveInside } from '../src/utils/path.ts';

test('resolveInside allows files within workspace', () => {
  const resolved = resolveInside('C:\\workspace', '.\\notes\\todo.txt');
  assert.equal(resolved, 'C:\\workspace\\notes\\todo.txt');
});

test('resolveInside blocks path traversal outside workspace', () => {
  assert.throws(() => resolveInside('C:\\workspace', '..\\secrets.txt'));
});

test('assertSafeHttpUrl blocks localhost targets', async () => {
  await assert.rejects(() => assertSafeHttpUrl('http://127.0.0.1:8080'));
});

test('assertSafeHttpUrl blocks non-http protocols', async () => {
  await assert.rejects(() => assertSafeHttpUrl('file:///C:/secret.txt'));
});
