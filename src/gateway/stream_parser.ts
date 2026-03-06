import type { LLMStreamChunk } from '../llm/provider.js';

type StreamChannel = LLMStreamChunk['channel'];

const OPEN_TAG = '<think>';
const CLOSE_TAG = '</think>';
const MAX_TAG_TAIL = CLOSE_TAG.length - 1;

export interface ParsedStreamChunk {
  channel: StreamChannel;
  token: string;
}

function findTagIndex(source: string, tag: string): number {
  return source.toLowerCase().indexOf(tag);
}

export function createReasoningStreamSplitter() {
  let mode: StreamChannel = 'content';
  let carry = '';

  function emitChunk(channel: StreamChannel, token: string, emit: (chunk: ParsedStreamChunk) => void): void {
    if (!token) {
      return;
    }

    emit({ channel, token });
  }

  function flushBuffered(emit: (chunk: ParsedStreamChunk) => void, flushAll: boolean): void {
    while (carry.length > 0) {
      const marker = mode === 'content' ? OPEN_TAG : CLOSE_TAG;
      const markerIndex = findTagIndex(carry, marker);

      if (markerIndex >= 0) {
        emitChunk(mode, carry.slice(0, markerIndex), emit);
        carry = carry.slice(markerIndex + marker.length);
        mode = mode === 'content' ? 'reasoning' : 'content';
        continue;
      }

      if (!flushAll) {
        const safeLength = carry.length - MAX_TAG_TAIL;
        if (safeLength <= 0) {
          return;
        }

        emitChunk(mode, carry.slice(0, safeLength), emit);
        carry = carry.slice(safeLength);
        return;
      }

      emitChunk(mode, carry, emit);
      carry = '';
    }
  }

  return {
    push(chunk: LLMStreamChunk, emit: (parsed: ParsedStreamChunk) => void): void {
      if (!chunk.token) {
        return;
      }

      if (chunk.channel === 'reasoning') {
        flushBuffered(emit, true);
        emitChunk('reasoning', chunk.token, emit);
        return;
      }

      carry += chunk.token;
      flushBuffered(emit, false);
    },
    flush(emit: (parsed: ParsedStreamChunk) => void): void {
      flushBuffered(emit, true);
    },
  };
}
