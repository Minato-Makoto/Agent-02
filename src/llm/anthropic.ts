// ═══════════════════════════════════════════════════
// Agent-02 — Anthropic Claude Provider
// ═══════════════════════════════════════════════════

import Anthropic from '@anthropic-ai/sdk';
import type { LLMProvider, LLMMessage, LLMResult, ToolDefinition } from './provider.js';
import { log } from '../gateway/eventbus.js';

export class AnthropicProvider implements LLMProvider {
    readonly name: string;
    private client: Anthropic;
    private model: string;

    constructor(apiKey: string, model: string) {
        this.name = `anthropic:${model}`;
        this.model = model;
        this.client = new Anthropic({ apiKey });
        log('info', 'llm', `Initialized ${this.name}`);
    }

    async chat(messages: LLMMessage[], tools?: ToolDefinition[]): Promise<LLMResult> {
        const systemMsg = messages.find(m => m.role === 'system')?.content || '';
        const chatMsgs = messages
            .filter(m => m.role !== 'system')
            .map(m => ({ role: m.role as 'user' | 'assistant', content: m.content }));

        const params: any = {
            model: this.model,
            max_tokens: 4096,
            system: systemMsg,
            messages: chatMsgs,
        };

        if (tools && tools.length > 0) {
            params.tools = tools.map(t => ({
                name: t.function.name,
                description: t.function.description,
                input_schema: t.function.parameters,
            }));
        }

        const res = await this.client.messages.create(params);
        let content = '';
        const toolCalls: any[] = [];

        for (const block of res.content) {
            if (block.type === 'text') content += block.text;
            if (block.type === 'tool_use') {
                toolCalls.push({ id: block.id, name: block.name, args: block.input as Record<string, any> });
            }
        }

        return { content, toolCalls: toolCalls.length > 0 ? toolCalls : undefined };
    }
}
