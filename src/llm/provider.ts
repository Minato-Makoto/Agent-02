// ═══════════════════════════════════════════════════
// Agent-02 — LLM Provider Interface & Factory
// ═══════════════════════════════════════════════════

import type { AppConfig } from '../config.js';
import type { ToolCallRequest } from '../gateway/eventbus.js';
import { OpenAICompatProvider } from './openai_compat.js';
import { AnthropicProvider } from './anthropic.js';
import { OllamaProvider } from './ollama.js';
import { LlamaCppProvider } from './llamacpp.js';

export interface LLMMessage {
    role: 'system' | 'user' | 'assistant' | 'tool';
    content: string;
    tool_calls?: any;
    tool_call_id?: string;
}

export interface LLMResult {
    content: string;
    toolCalls?: ToolCallRequest[];
}

export interface ToolDefinition {
    type: 'function';
    function: {
        name: string;
        description: string;
        parameters: Record<string, any>;
    };
}

export interface LLMProvider {
    name: string;
    chat(messages: LLMMessage[], tools?: ToolDefinition[]): Promise<LLMResult>;
}

// Base URL mappings for OpenAI-compatible providers
const PROVIDER_URLS: Record<string, string> = {
    openai: 'https://api.openai.com/v1',
    deepseek: 'https://api.deepseek.com/v1',
    gemini: 'https://generativelanguage.googleapis.com/v1beta/openai',
    mistral: 'https://api.mistral.ai/v1',
    groq: 'https://api.groq.com/openai/v1',
    openrouter: 'https://openrouter.ai/api/v1',
    grok: 'https://api.x.ai/v1',
};

let _provider: LLMProvider | null = null;

export function getLLMProvider(cfg: AppConfig): LLMProvider | null {
    if (_provider) return _provider;
    const { provider, apiKey, model, baseUrl, ggufPath } = cfg.llm;
    if (!provider) return null;

    try {
        if (provider === 'anthropic') {
            _provider = new AnthropicProvider(apiKey, model || 'claude-sonnet-4-20250514');
        } else if (provider === 'ollama') {
            _provider = new OllamaProvider(model || 'llama3');
        } else if (provider === 'llamacpp') {
            _provider = new LlamaCppProvider(ggufPath || '');
        } else {
            // OpenAI-compatible (openai, deepseek, gemini, mistral, groq, openrouter, grok)
            const url = baseUrl || PROVIDER_URLS[provider] || PROVIDER_URLS.openai;
            _provider = new OpenAICompatProvider(apiKey, model || 'gpt-4o', url, provider);
        }
    } catch (err: any) {
        console.error(`[LLM] Failed to initialize provider "${provider}": ${err.message}`);
        return null;
    }

    return _provider;
}

export function resetProvider(): void {
    _provider = null;
}
