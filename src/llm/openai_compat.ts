// ═══════════════════════════════════════════════════
// Agent-02 — OpenAI-Compatible Provider
// Supports: OpenAI, DeepSeek, Gemini, Mistral, Groq, OpenRouter, Grok
// ═══════════════════════════════════════════════════

import OpenAI from 'openai';
import type { LLMProvider, LLMMessage, LLMResult, ToolDefinition } from './provider.js';
import { log } from '../gateway/eventbus.js';

export class OpenAICompatProvider implements LLMProvider {
    readonly name: string;
    private client: OpenAI;
    private model: string;

    constructor(apiKey: string, model: string, baseURL: string, providerName: string) {
        this.name = `${providerName}:${model}`;
        this.model = model;
        this.client = new OpenAI({ apiKey, baseURL });
        log('info', 'llm', `Initialized ${this.name} (${baseURL})`);
    }

    async chat(messages: LLMMessage[], tools?: ToolDefinition[]): Promise<LLMResult> {
        const params: any = {
            model: this.model,
            messages: messages.map(m => ({
                role: m.role,
                content: m.content,
                ...(m.tool_calls ? { tool_calls: m.tool_calls } : {}),
                ...(m.tool_call_id ? { tool_call_id: m.tool_call_id } : {}),
            })),
            max_tokens: 4096,
            temperature: 0.7,
        };

        if (tools && tools.length > 0) {
            params.tools = tools;
            params.tool_choice = 'auto';
        }

        const res = await this.client.chat.completions.create(params);
        const choice = res.choices[0];
        const msg = choice.message;

        const result: LLMResult = { content: msg.content || '' };

        if (msg.tool_calls && msg.tool_calls.length > 0) {
            result.toolCalls = msg.tool_calls.map(tc => ({
                id: tc.id,
                name: tc.function.name,
                args: JSON.parse(tc.function.arguments || '{}'),
            }));
        }

        return result;
    }
}
