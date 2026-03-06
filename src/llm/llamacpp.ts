// ═══════════════════════════════════════════════════
// Agent-02 — llama.cpp Local Provider
// Auto-detects llama-server.exe from adjacent llama.cpp folder
// ═══════════════════════════════════════════════════

import type { LLMProvider, LLMMessage, LLMResult, LLMRequestOptions, ToolDefinition, LLMStreamChunk } from './provider.js';
import { log } from '../gateway/eventbus.js';
import { execSync, spawn, type ChildProcess } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';
import { LLAMA_SERVER_CANDIDATES, MODELS_DIR } from '../paths.js';
import { freePortIfOccupied } from '../runtime/ports.js';

export class LlamaCppProvider implements LLMProvider {
    readonly name: string;
    private ggufPath: string;
    private serverUrl: string;
    private serverProcess: ChildProcess | null = null;
    private spawnedServer = false;

    constructor(ggufPath: string, serverUrl = 'http://127.0.0.1:8081') {
        this.name = `llamacpp:${path.basename(ggufPath)}`;
        this.ggufPath = ggufPath;
        this.serverUrl = serverUrl;
        log('info', 'llamacpp', `Provider created for model: ${ggufPath}`);
    }

    private getServerEndpoint(): { host: string; port: number; managed: boolean } {
        try {
            const url = new URL(this.serverUrl);
            const host = url.hostname || '127.0.0.1';
            const port = Number(url.port || (url.protocol === 'https:' ? 443 : 80));
            const managed = ['127.0.0.1', 'localhost'].includes(host) && Number.isInteger(port) && port > 0;
            return { host, port, managed };
        } catch {
            return { host: '127.0.0.1', port: 8081, managed: true };
        }
    }

    private resolveModelPath(): string {
        const rawValue = (this.ggufPath || '').trim();
        if (!rawValue) {
            return rawValue;
        }

        const candidates = [
            rawValue,
            path.resolve(rawValue),
            path.join(MODELS_DIR, rawValue),
            path.join(MODELS_DIR, path.basename(rawValue)),
        ];

        for (const candidate of candidates) {
            if (candidate && fs.existsSync(candidate)) {
                if (candidate !== this.ggufPath) {
                    log('info', 'llamacpp', `Resolved GGUF path to: ${candidate}`);
                }
                this.ggufPath = candidate;
                return candidate;
            }
        }

        return rawValue;
    }

    private findServerBinary(): string {
        for (const p of LLAMA_SERVER_CANDIDATES) {
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
            LLAMA_SERVER_CANDIDATES.map(p => `  - ${p}`).join('\n') +
            '\n\nDownload from: https://github.com/ggerganov/llama.cpp/releases'
        );
    }

    private async ensureServer(): Promise<void> {
        const endpoint = this.getServerEndpoint();

        // Check if already running
        if (this.serverProcess?.pid) {
            try {
                const res = await fetch(`${this.serverUrl}/health`, { signal: AbortSignal.timeout(2000) });
                if (res.ok) {
                    log('info', 'llamacpp', 'llama-server already running');
                    return;
                }
            } catch { }
        } else if (!endpoint.managed) {
            try {
                const res = await fetch(`${this.serverUrl}/health`, { signal: AbortSignal.timeout(2000) });
                if (res.ok) {
                    log('info', 'llamacpp', `Using external llama-server at ${this.serverUrl}`);
                    return;
                }
            } catch { }

            throw new Error(`llama-server is unreachable at ${this.serverUrl}. Start it manually or switch back to the local default URL.`);
        } else {
            const killedPids = await freePortIfOccupied(endpoint.port);
            if (killedPids.length > 0) {
                log('warn', 'llamacpp', `Cleared stale llama-server process(es) on port ${endpoint.port}: ${killedPids.join(', ')}`);
            }
        }

        // Validate GGUF path
        const resolvedModelPath = this.resolveModelPath();
        if (!resolvedModelPath || !fs.existsSync(resolvedModelPath)) {
            throw new Error(`GGUF model not found: "${this.ggufPath}". Check Settings > GGUF Path.`);
        }

        // Find and start llama-server
        const serverBin = this.findServerBinary();
        log('info', 'llamacpp', `Starting llama-server with: ${path.basename(resolvedModelPath)}`);

        const args = [
            '-m', resolvedModelPath,
            '--host', endpoint.host,
            '--port', String(endpoint.port),
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
        this.spawnedServer = true;

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
            this.spawnedServer = false;
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

    async chat(messages: LLMMessage[], _tools?: ToolDefinition[], options?: LLMRequestOptions): Promise<LLMResult> {
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
                signal: options?.signal,
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
    async chatStream(
        messages: LLMMessage[],
        onChunk: (chunk: LLMStreamChunk) => void,
        _tools?: ToolDefinition[],
        options?: LLMRequestOptions,
    ): Promise<void> {
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
            signal: options?.signal,
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
                    if (delta?.reasoning_content) {
                        onChunk({ channel: 'reasoning', token: delta.reasoning_content });
                    }
                    if (delta?.content) {
                        onChunk({ channel: 'content', token: delta.content });
                    }
                } catch { }
            }
        }
    }

    async close(): Promise<void> {
        if (!this.spawnedServer || !this.serverProcess?.pid) {
            return;
        }

        const pid = this.serverProcess.pid;
        this.spawnedServer = false;

        try {
            if (process.platform === 'win32') {
                execSync(`taskkill /PID ${pid} /T /F`, { stdio: 'ignore' });
            } else {
                this.serverProcess.kill('SIGTERM');
            }
            log('info', 'llamacpp', `Stopped managed llama-server process ${pid}`);
        } catch (err: any) {
            log('warn', 'llamacpp', `Failed to stop llama-server cleanly: ${err.message}`);
        } finally {
            this.serverProcess = null;
        }
    }
}
