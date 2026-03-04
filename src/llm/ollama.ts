// ═══════════════════════════════════════════════════
// Agent-02 — Ollama Local Provider
// ═══════════════════════════════════════════════════

import type { LLMProvider, LLMMessage, LLMResult, ToolDefinition } from './provider.js';
import { log } from '../gateway/eventbus.js';

export class OllamaProvider implements LLMProvider {
    readonly name: string;
    private model: string;
    private baseUrl: string;

    constructor(model: string, baseUrl = 'http://127.0.0.1:11434') {
        this.name = `ollama:${model}`;
        this.model = model;
        this.baseUrl = baseUrl;
        log('info', 'llm', `Initialized ${this.name} at ${baseUrl}`);
    }

    async chat(messages: LLMMessage[], tools?: ToolDefinition[]): Promise<LLMResult> {
        const body: any = {
            model: this.model,
            messages: messages.map(m => ({ role: m.role, content: m.content })),
            stream: false,
        };

        if (tools && tools.length > 0) {
            body.tools = tools;
        }

        const res = await fetch(`${this.baseUrl}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });

        if (!res.ok) {
            const err = await res.text();
            throw new Error(`Ollama error ${res.status}: ${err}`);
        }

        const data: any = await res.json();
        const msg = data.message || {};

        const result: LLMResult = { content: msg.content || '' };

        if (msg.tool_calls && msg.tool_calls.length > 0) {
            result.toolCalls = msg.tool_calls.map((tc: any) => ({
                id: tc.id || `ollama_${Date.now()}`,
                name: tc.function.name,
                args: tc.function.arguments || {},
            }));
        }

        return result;
    }
}
