// ═══════════════════════════════════════════════════
// Agent-02 — Message Router (with consent flow)
// ═══════════════════════════════════════════════════

import { bus, log, type AgentMessage, type ToolCallRequest } from './eventbus.js';
import { sessions, type ChatMessage } from './session.js';
import { getLLMProvider, type LLMProvider } from '../llm/provider.js';
import { skillRegistry } from '../skills/registry.js';
import { loadConfig } from '../config.js';
import { addConsentRequest, resolveConsent } from '../db.js';
import * as crypto from 'crypto';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const INSTRUCTIONS_DIR = path.join(__dirname, '..', '..', 'data', 'instructions');

function getSystemPrompt(): string {
    try {
        const sysPath = path.join(INSTRUCTIONS_DIR, 'system.md');
        if (fs.existsSync(sysPath)) {
            return fs.readFileSync(sysPath, 'utf8').trim();
        }
    } catch { }
    return `You are Agent-02, a helpful AI assistant running as a self-hosted gateway.
You have access to tools that the user has explicitly enabled. Before executing any potentially dangerous action, you will ask for confirmation.
Always be helpful, concise, and security-conscious. Never expose internal system details like API keys or file paths outside the allowed workspace.`;
}

const MAX_TOOL_ROUNDS = 5;
const pendingConsents = new Map<string, { resolve: (approved: boolean) => void }>();

export async function handleMessage(msg: AgentMessage): Promise<string> {
    const cfg = loadConfig();
    const provider = getLLMProvider(cfg);
    if (!provider) {
        return 'No AI model configured. Please set up your AI backend in Settings.';
    }

    const sessionId = sessions.getOrCreate(msg.platform, msg.userId, msg.userName);
    const history = sessions.hydrate(sessionId);
    sessions.save(sessionId, 'user', msg.content);

    const sysPrompt = getSystemPrompt();

    const messages: ChatMessage[] = [
        { role: 'system', content: sysPrompt },
        ...history,
        { role: 'user', content: msg.content },
    ];

    const tools = skillRegistry.getToolDefinitions();
    let response = '';

    try {
        for (let round = 0; round < MAX_TOOL_ROUNDS; round++) {
            const result = await provider.chat(messages, tools.length > 0 ? tools : undefined);

            if (!result.toolCalls || result.toolCalls.length === 0) {
                response = result.content || '(no response)';
                break;
            }

            // Handle tool calls
            messages.push({
                role: 'assistant',
                content: result.content || '',
                tool_calls: result.toolCalls,
            });

            for (const tc of result.toolCalls) {
                log('info', 'router', `Tool call: ${tc.name}`, tc.args);
                bus.emitEvent('tool:call', { ...tc, sessionId });

                const skill = skillRegistry.getSkill(tc.name);
                let toolResult: string;

                if (skill?.requiresConsent) {
                    // Human-in-the-Loop: pause and ask for approval
                    toolResult = await requestConsent(sessionId, tc);
                } else {
                    toolResult = await skillRegistry.execute(tc.name, tc.args);
                }

                messages.push({ role: 'tool', content: toolResult, tool_call_id: tc.id });
                sessions.save(sessionId, 'tool', toolResult, undefined, tc.id);
                bus.emitEvent('tool:result', { sessionId, toolCallId: tc.id, result: toolResult });
            }
        }
    } catch (err: any) {
        log('error', 'router', `LLM error: ${err.message}`);
        response = `Error: ${err.message}`;
    }

    sessions.save(sessionId, 'assistant', response);
    return response;
}

// ── Streaming version for SSE/WS ──
export async function streamChat(
    msg: AgentMessage,
    onToken: (token: string, done: boolean) => void,
    signal?: AbortSignal
): Promise<void> {
    const cfg = loadConfig();
    const provider = getLLMProvider(cfg);
    if (!provider) {
        onToken('No AI model configured. Please set up your AI backend in Settings.', false);
        onToken('', true);
        return;
    }

    const sessionId = sessions.getOrCreate(msg.platform, msg.userId, msg.userName);
    const history = sessions.hydrate(sessionId);
    sessions.save(sessionId, 'user', msg.content);

    const sysPrompt = getSystemPrompt();

    const messages: ChatMessage[] = [
        { role: 'system', content: sysPrompt },
        ...history,
        { role: 'user', content: msg.content },
    ];

    let fullResponse = '';
    try {
        // Use streaming if provider supports it
        if ('chatStream' in provider && typeof (provider as any).chatStream === 'function') {
            await (provider as any).chatStream(messages, (token: string) => {
                fullResponse += token;
                onToken(token, false);
            });
        } else {
            // Fallback: non-streaming
            const result = await provider.chat(messages);
            fullResponse = result.content || '(no response)';
            onToken(fullResponse, false);
        }
    } catch (err: any) {
        log('error', 'router', `Stream error: ${err.message}`);
        fullResponse = `Error: ${err.message}`;
        onToken(fullResponse, false);
    }

    sessions.save(sessionId, 'assistant', fullResponse);
    onToken('', true);
}

async function requestConsent(sessionId: string, tc: ToolCallRequest): Promise<string> {
    const consentId = crypto.randomUUID();
    addConsentRequest(consentId, sessionId, tc.name, tc.args);

    bus.emitEvent('consent:request', {
        consentId,
        sessionId,
        skillName: tc.name,
        args: tc.args,
        status: 'pending',
    });

    log('warn', 'consent', `Waiting for approval: ${tc.name}(${JSON.stringify(tc.args).slice(0, 100)})`);

    // Wait for approval (max 5 minutes)
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
        consentId,
        sessionId,
        skillName: tc.name,
        args: tc.args,
        status: approved ? 'approved' : 'denied',
    });

    if (!approved) {
        return `[DENIED] User denied execution of ${tc.name}. Action was not performed.`;
    }

    return await skillRegistry.execute(tc.name, tc.args);
}

// Called from API when user approves/denies
export function resolveConsentRequest(consentId: string, approved: boolean): void {
    const pending = pendingConsents.get(consentId);
    if (pending) {
        pending.resolve(approved);
        pendingConsents.delete(consentId);
    }
}

// Initialize router listeners
export function initRouter(): void {
    bus.onEvent('message:in', async (msg) => {
        try {
            const response = await handleMessage(msg);
            bus.emitEvent('message:out', {
                sessionId: sessions.getOrCreate(msg.platform, msg.userId),
                platform: msg.platform,
                content: response,
            });
        } catch (err: any) {
            bus.emitEvent('error', { source: 'router', error: err.message });
        }
    });

    log('info', 'router', 'Message router initialized with consent flow');
}
