import test from 'node:test';
import assert from 'node:assert/strict';
import { createReasoningStreamSplitter } from '../src/gateway/stream_parser.ts';
import type { LLMStreamChunk } from '../src/llm/provider.ts';

function collect(chunks: LLMStreamChunk[]) {
  const splitter = createReasoningStreamSplitter();
  const result: Array<{ channel: 'content' | 'reasoning'; token: string }> = [];

  for (const chunk of chunks) {
    splitter.push(chunk, (parsed) => result.push(parsed));
  }

  splitter.flush((parsed) => result.push(parsed));
  return result;
}

function collectMerged(chunks: LLMStreamChunk[]) {
  const merged: Array<{ channel: 'content' | 'reasoning'; token: string }> = [];

  for (const chunk of collect(chunks)) {
    const previous = merged[merged.length - 1];
    if (previous?.channel === chunk.channel) {
      previous.token += chunk.token;
      continue;
    }

    merged.push({ ...chunk });
  }

  return merged;
}

test('splits think tags from content stream', () => {
  const parsed = collectMerged([
    { channel: 'content', token: '<think>plan step 1\nplan step 2</think>\nFinal answer.' },
  ]);

  assert.deepEqual(parsed, [
    { channel: 'reasoning', token: 'plan step 1\nplan step 2' },
    { channel: 'content', token: '\nFinal answer.' },
  ]);
});

test('handles think tags split across streamed tokens', () => {
  const parsed = collectMerged([
    { channel: 'content', token: '<thi' },
    { channel: 'content', token: 'nk>alpha' },
    { channel: 'content', token: ' beta</th' },
    { channel: 'content', token: 'ink>Answer' },
  ]);

  assert.deepEqual(parsed, [
    { channel: 'reasoning', token: 'alpha beta' },
    { channel: 'content', token: 'Answer' },
  ]);
});

test('passes explicit reasoning chunks through unchanged', () => {
  const parsed = collectMerged([
    { channel: 'reasoning', token: 'inner thoughts' },
    { channel: 'content', token: 'Visible answer' },
  ]);

  assert.deepEqual(parsed, [
    { channel: 'reasoning', token: 'inner thoughts' },
    { channel: 'content', token: 'Visible answer' },
  ]);
});
