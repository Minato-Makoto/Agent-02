// ═══════════════════════════════════════════════════
// Agent-02 — llama.cpp Local Provider
// Auto-detects llama-server.exe from adjacent llama.cpp folder
// ═══════════════════════════════════════════════════

import type { LLMProvider, LLMMessage, LLMResult } from './provider.js';
import { log } from '../gateway/eventbus.js';
import { execSync, spawn, type ChildProcess } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export class LlamaCppProvider implements LLMProvider {
    readonly name: string;
    private ggufPath: string;
    private serverUrl = 'http://127.0.0.1:8081';
    private serverProcess: ChildProcess | null = null;

    constructor(ggufPath: string) {
        this.name = `llamacpp:${path.basename(ggufPath)}`;
        this.ggufPath = ggufPath;
        log('info', 'llamacpp', `Provider created for model: ${ggufPath}`);
    }

    private findServerBinary(): string {
        // Search order: adjacent llama.cpp folder, PATH, current dir
        const searchPaths = [
            // Relative to agent-02 project root -> sibling llama.cpp folder
            path.resolve(__dirname, '..', '..', '..', 'llama.cpp', 'llama-server.exe'),
            path.resolve(__dirname, '..', '..', '..', 'llama.cpp', 'llama-server'),
            // Common Windows locations
            'C:\\llama.cpp\\llama-server.exe',
            // In PATH
            'llama-server',
        ];

        for (const p of searchPaths) {
            try {
                if (fs.existsSync(p)) {
                    log('info', 'llamacpp', `Found llama-server at: ${p}`);
                    return p;
                }
            } catch { }
            // Try execute check for PATH-based entries
            try {
                execSync(`"${p}" --version`, { timeout: 3000, stdio: 'ignore' });
                log('info', 'llamacpp', `Found llama-server in PATH: ${p}`);
                return p;
            } catch { }
        }

        throw new Error(
            'llama-server not found! Searched:\n' +
            searchPaths.map(p => `  - ${p}`).join('\n') +
            '\n\nDownload from: https://github.com/ggerganov/llama.cpp/releases'
        );
    }

    private async ensureServer(): Promise<void> {
        // Check if already running
        try {
            const res = await fetch(`${this.serverUrl}/health`, { signal: AbortSignal.timeout(2000) });
            if (res.ok) {
                log('info', 'llamacpp', 'llama-server already running');
                return;
            }
        } catch { }

        // Validate GGUF path
        if (!this.ggufPath || !fs.existsSync(this.ggufPath)) {
            throw new Error(`GGUF model not found: "${this.ggufPath}". Check Settings > GGUF Path.`);
        }

        // Find and start llama-server
        const serverBin = this.findServerBinary();
        log('info', 'llamacpp', `Starting llama-server with: ${path.basename(this.ggufPath)}`);

        const args = [
            '-m', this.ggufPath,
            '--host', '127.0.0.1',
            '--port', '8081',
            '-c', '4096',
            '-ngl', '99',  // Offload all layers to GPU
        ];

        log('info', 'llamacpp', `Command: ${serverBin} ${args.join(' ')}`);

        // Set CWD to llama.cpp folder so DLLs are found
        const serverDir = path.dirname(serverBin);

        this.serverProcess = spawn(serverBin, args, {
            stdio: ['ignore', 'pipe', 'pipe'],
            detached: false,
            cwd: serverDir,
        });

        // Capture llama-server output for GPU/CPU diagnostics
        this.serverProcess.stderr?.on('data', (chunk: Buffer) => {
            const line = chunk.toString().trim();
            if (line) log('info', 'llamacpp', line);
        });

        this.serverProcess.stdout?.on('data', (chunk: Buffer) => {
            const line = chunk.toString().trim();
            if (line) log('info', 'llamacpp', line);
        });

        this.serverProcess.on('error', (err: Error) => {
            log('error', 'llamacpp', `Server process error: ${err.message}`);
        });

        this.serverProcess.on('exit', (code) => {
            if (code !== null && code !== 0) {
                log('error', 'llamacpp', `Server exited with code ${code}`);
            }
            this.serverProcess = null;
        });

        // Wait for server to be ready (up to 60 seconds for large models)
        log('info', 'llamacpp', 'Waiting for llama-server to load model...');
        for (let i = 0; i < 60; i++) {
            await new Promise(r => setTimeout(r, 1000));
            try {
                const res = await fetch(`${this.serverUrl}/health`, { signal: AbortSignal.timeout(2000) });
                if (res.ok) {
                    log('info', 'llamacpp', `llama-server ready! (took ${i + 1}s)`);
                    return;
                }
            } catch { }
            if (i % 10 === 9) {
                log('info', 'llamacpp', `Still loading model... (${i + 1}s)`);
            }
        }
        throw new Error('llama-server failed to start within 60 seconds. Check if model is valid.');
    }

    async chat(messages: LLMMessage[]): Promise<LLMResult> {
        await this.ensureServer();

        try {
            const res = await fetch(`${this.serverUrl}/v1/chat/completions`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    messages: messages.map(m => ({ role: m.role, content: m.content })),
                    max_tokens: 2048,
                    temperature: 0.7,
                }),
            });

            if (!res.ok) {
                const errText = await res.text();
                throw new Error(`Server error ${res.status}: ${errText}`);
            }

            const data: any = await res.json();
            return { content: data.choices?.[0]?.message?.content || '(no response from model)' };
        } catch (err: any) {
            log('error', 'llamacpp', `Inference error: ${err.message}`);
            return { content: `Error: ${err.message}` };
        }
    }

    // ── Streaming chat ──
    async chatStream(messages: LLMMessage[], onToken: (token: string) => void): Promise<void> {
        await this.ensureServer();

        const res = await fetch(`${this.serverUrl}/v1/chat/completions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                messages: messages.map(m => ({ role: m.role, content: m.content })),
                max_tokens: 2048,
                temperature: 0.7,
                stream: true,
            }),
        });

        if (!res.ok) {
            const errText = await res.text();
            throw new Error(`Server error ${res.status}: ${errText}`);
        }

        if (!res.body) throw new Error('No response body for streaming');

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed || !trimmed.startsWith('data: ')) continue;
                const data = trimmed.slice(6);
                if (data === '[DONE]') return;

                try {
                    const json = JSON.parse(data);
                    const delta = json.choices?.[0]?.delta;
                    // Include both content and reasoning_content (thinking)
                    const token = delta?.content || delta?.reasoning_content || '';
                    if (token) onToken(token);
                } catch { }
            }
        }
    }
}
