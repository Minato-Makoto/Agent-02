// ═══════════════════════════════════════════════════
// Agent-02 — Anthropic Claude Provider
// ═══════════════════════════════════════════════════

import Anthropic from '@anthropic-ai/sdk';
import type { LLMProvider, LLMMessage, LLMResult, ToolDefinition, LLMRequestOptions } from './provider.js';
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

    async chat(messages: LLMMessage[], tools?: ToolDefinition[], options?: LLMRequestOptions): Promise<LLMResult> {
        const systemMsg = messages.find(m => m.role === 'system')?.content || '';
        const chatMsgs = messages
            .filter(m => m.role !== 'system')
            .map((m) => {
                if (m.role === 'assistant') {
                    const blocks: any[] = [];
                    if (m.content?.trim()) {
                        blocks.push({ type: 'text', text: m.content });
                    }

                    for (const toolCall of m.tool_calls ?? []) {
                        blocks.push({
                            type: 'tool_use',
                            id: toolCall.id,
                            name: toolCall.name,
                            input: toolCall.args ?? {},
                        });
                    }

                    return { role: 'assistant' as const, content: blocks };
                }

                if (m.role === 'tool') {
                    return {
                        role: 'user' as const,
                        content: [{
                            type: 'tool_result',
                            tool_use_id: m.tool_call_id || '',
                            content: m.content,
                        }],
                    };
                }

                return { role: 'user' as const, content: m.content };
            })
            .filter((message) => Array.isArray(message.content) ? message.content.length > 0 : true);

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

        const res = await this.client.messages.create(params, { signal: options?.signal } as any);
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
