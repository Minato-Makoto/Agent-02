import * as crypto from 'crypto';
import { getSystemPrompt, loadConfig } from '../config.js';
import { addConsentRequest, resolveConsent } from '../db.js';
import { getLLMProvider, type LLMStreamChunk } from '../llm/provider.js';
import { skillRegistry } from '../skills/registry.js';
import { bus, log, type AgentMessage, type ToolCallRequest } from './eventbus.js';
import { sessions, type ChatMessage } from './session.js';
import { createReasoningStreamSplitter } from './stream_parser.js';

const MAX_TOOL_ROUNDS = 8;
const pendingConsents = new Map<string, { resolve: (approved: boolean) => void }>();

function abortIfNeeded(signal?: AbortSignal): void {
  if (signal?.aborted) {
    throw new Error('Request aborted by user.');
  }
}

function buildMessages(msg: AgentMessage): { sessionId: string; messages: ChatMessage[] } {
  const sessionId = sessions.getOrCreate(msg.platform, msg.userId, msg.userName);
  const history = sessions.hydrate(sessionId);
  sessions.save(sessionId, 'user', msg.content);

  return {
    sessionId,
    messages: [
      { role: 'system', content: getSystemPrompt() },
      ...history,
      { role: 'user', content: msg.content },
    ],
  };
}

function splitIntoChunks(text: string): string[] {
  const chunks = text.match(/.{1,40}(\s+|$)|\S+/g);
  return chunks && chunks.length > 0 ? chunks : [text];
}

async function executeToolCall(sessionId: string, toolCall: ToolCallRequest): Promise<string> {
  log('info', 'router', `Tool call: ${toolCall.name}`, toolCall.args);
  bus.emitEvent('tool:call', { ...toolCall, sessionId });

  const skill = skillRegistry.getSkill(toolCall.name);
  if (!skill) {
    return `Error: Unknown skill "${toolCall.name}"`;
  }

  if (skill.requiresConsent) {
    return requestConsent(sessionId, toolCall);
  }

  return skillRegistry.execute(toolCall.name, toolCall.args);
}

async function runConversation(msg: AgentMessage, signal?: AbortSignal): Promise<{ sessionId: string; response: string }> {
  const provider = getLLMProvider(loadConfig());
  if (!provider) {
    return {
      sessionId: sessions.getOrCreate(msg.platform, msg.userId, msg.userName),
      response: 'No AI model configured. Please set up your AI backend in Settings.',
    };
  }

  const { sessionId, messages } = buildMessages(msg);
  const tools = skillRegistry.getToolDefinitions();
  let response = '';

  try {
    for (let round = 0; round < MAX_TOOL_ROUNDS; round++) {
      abortIfNeeded(signal);
      const result = await provider.chat(messages, tools.length > 0 ? tools : undefined, { signal });

      if (!result.toolCalls || result.toolCalls.length === 0) {
        response = result.content || '(no response)';
        break;
      }

      messages.push({
        role: 'assistant',
        content: result.content || '',
        tool_calls: result.toolCalls,
      });
      sessions.save(sessionId, 'assistant', result.content || '', result.toolCalls);

      for (const toolCall of result.toolCalls) {
        abortIfNeeded(signal);
        const toolResult = await executeToolCall(sessionId, toolCall);
        messages.push({ role: 'tool', content: toolResult, tool_call_id: toolCall.id });
        sessions.save(sessionId, 'tool', toolResult, undefined, toolCall.id);
        bus.emitEvent('tool:result', { sessionId, toolCallId: toolCall.id, result: toolResult });
      }
    }
  } catch (err: any) {
    if (signal?.aborted) {
      throw err;
    }

    log('error', 'router', `LLM error: ${err.message}`);
    response = `Error: ${err.message}`;
  }

  sessions.save(sessionId, 'assistant', response);
  return { sessionId, response };
}

export async function handleMessage(msg: AgentMessage): Promise<string> {
  const { response } = await runConversation(msg);
  return response;
}

export interface StreamEvent {
  channel: 'content' | 'reasoning';
  token: string;
  done: boolean;
}

export async function streamChat(
  msg: AgentMessage,
  onToken: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  try {
    const cfg = loadConfig();
    const provider = getLLMProvider(cfg);
    if (!provider) {
      onToken({ channel: 'content', token: 'No AI model configured. Please set up your AI backend in Settings.', done: false });
      onToken({ channel: 'content', token: '', done: true });
      return;
    }

    if (provider.chatStream && cfg.llm.provider === 'llamacpp') {
      const { sessionId, messages } = buildMessages(msg);
      let reasoningBuffer = '';
      let contentBuffer = '';
      const splitter = createReasoningStreamSplitter();

      const emitChunk = (chunk: LLMStreamChunk) => {
        abortIfNeeded(signal);

        if (chunk.channel === 'reasoning') {
          reasoningBuffer += chunk.token;
        } else {
          contentBuffer += chunk.token;
        }

        onToken({ channel: chunk.channel, token: chunk.token, done: false });
      };

      await provider.chatStream(
        messages,
        (chunk: LLMStreamChunk) => {
          splitter.push(chunk, emitChunk);
        },
        undefined,
        { signal },
      );
      splitter.flush(emitChunk);

      const persistedResponse = reasoningBuffer.trim()
        ? `<think>\n${reasoningBuffer.trim()}\n</think>\n\n${contentBuffer || '(no response)'}`
        : (contentBuffer || '(no response)');
      sessions.save(sessionId, 'assistant', persistedResponse);
      onToken({ channel: 'content', token: '', done: true });
      return;
    }

    const { response } = await runConversation(msg, signal);
    for (const chunk of splitIntoChunks(response)) {
      abortIfNeeded(signal);
      onToken({ channel: 'content', token: chunk, done: false });
      await new Promise((resolve) => setTimeout(resolve, 12));
    }

    onToken({ channel: 'content', token: '', done: true });
  } catch (err: any) {
    if (signal?.aborted) {
      log('info', 'router', `Stream aborted for session ${msg.sessionId}`);
      onToken({ channel: 'content', token: '', done: true });
      return;
    }

    log('error', 'router', `Stream error: ${err.message}`);
    onToken({ channel: 'content', token: `Error: ${err.message}`, done: false });
    onToken({ channel: 'content', token: '', done: true });
  }
}

async function requestConsent(sessionId: string, toolCall: ToolCallRequest): Promise<string> {
  const consentId = crypto.randomUUID();
  addConsentRequest(consentId, sessionId, toolCall.name, toolCall.args);

  const event = {
    id: consentId,
    consentId,
    sessionId,
    skillName: toolCall.name,
    args: toolCall.args,
    status: 'pending' as const,
  };

  bus.emitEvent('consent:request', event);
  log('warn', 'consent', `Waiting for approval: ${toolCall.name}(${JSON.stringify(toolCall.args).slice(0, 120)})`);

  const approved = await new Promise<boolean>((resolve) => {
    pendingConsents.set(consentId, { resolve });
    setTimeout(() => {
      if (pendingConsents.has(consentId)) {
        pendingConsents.delete(consentId);
        resolve(false);
      }
    }, 5 * 60 * 1000);
  });

  resolveConsent(consentId, approved);
  bus.emitEvent('consent:resolve', {
    ...event,
    status: approved ? 'approved' : 'denied',
  });

  if (!approved) {
    return `[DENIED] User denied execution of ${toolCall.name}. Action was not performed.`;
  }

  return skillRegistry.execute(toolCall.name, toolCall.args);
}

export function resolveConsentRequest(consentId: string, approved: boolean): void {
  const pending = pendingConsents.get(consentId);
  if (!pending) {
    return;
  }

  pending.resolve(approved);
  pendingConsents.delete(consentId);
}

export function initRouter(): void {
  bus.onEvent('message:in', async (msg) => {
    try {
      const response = await handleMessage(msg);
      bus.emitEvent('message:out', {
        sessionId: sessions.getOrCreate(msg.platform, msg.userId, msg.userName),
        platform: msg.platform,
        content: response,
      });
    } catch (err: any) {
      bus.emitEvent('error', { source: 'router', error: err.message });
    }
  });

  log('info', 'router', 'Message router initialized');
}
