// ═══════════════════════════════════════════════════
// Agent-02 — Fastify API Server + WebSocket
// ═══════════════════════════════════════════════════

import Fastify from 'fastify';
import fastifyStatic from '@fastify/static';
import fastifyWebsocket from '@fastify/websocket';
import * as path from 'path';
import { fileURLToPath } from 'url';
import { bus, log } from '../gateway/eventbus.js';
import { loadConfig, saveConfig } from '../config.js';
import { addLog, getRecentLogs, getAllSessions, getHistory, getPendingConsents } from '../db.js';
import { resolveConsentRequest } from '../gateway/router.js';
import { WhatsAppCloudAdapter } from '../adapters/whatsapp_cloud.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export async function startApiServer(whatsappAdapter?: WhatsAppCloudAdapter): Promise<void> {
    const cfg = loadConfig();
    const app = Fastify({ logger: false });

    await app.register(fastifyWebsocket);

    // Serve React UI static files
    const uiPath = path.join(__dirname, '..', '..', 'ui', 'dist');
    try {
        await app.register(fastifyStatic, { root: uiPath, prefix: '/' });
    } catch {
        log('warn', 'api', `UI not built at ${uiPath}. Run 'npm run ui:build' first.`);
    }

    // ── REST API ──

    app.get('/api/status', async () => ({
        status: 'running',
        version: '2.0.0',
        uptime: process.uptime(),
        memory: process.memoryUsage(),
        llm: { provider: cfg.llm.provider, model: cfg.llm.model },
    }));

    app.get('/api/config', async () => {
        const c = loadConfig();
        // Mask secrets
        return {
            ...c,
            llm: { ...c.llm, apiKey: c.llm.apiKey ? '****' + c.llm.apiKey.slice(-4) : '' },
            connectors: Object.fromEntries(
                Object.entries(c.connectors).map(([k, v]) => [k, {
                    ...v,
                    token: v.token ? '****' : '',
                    accessToken: v.accessToken ? '****' : '',
                    appSecret: v.appSecret ? '****' : '',
                }])
            ),
        };
    });

    app.post('/api/config', async (req) => {
        const updates = req.body as any;
        saveConfig(updates);
        return { ok: true };
    });

    app.get('/api/sessions', async () => getAllSessions());

    app.get('/api/sessions/:id/messages', async (req) => {
        const { id } = req.params as any;
        return getHistory(id, 100);
    });

    app.get('/api/logs', async (req) => {
        const { limit } = req.query as any;
        return getRecentLogs(Number(limit) || 100);
    });

    // ── Consent API ──
    app.get('/api/consents', async () => getPendingConsents());

    app.post('/api/consents/:id', async (req) => {
        const { id } = req.params as any;
        const { approved } = req.body as any;
        resolveConsentRequest(id, approved === true);
        return { ok: true };
    });

    // ── WhatsApp Webhook ──
    if (whatsappAdapter) {
        app.get('/api/webhooks/whatsapp', async (req, reply) => {
            const { 'hub.mode': mode, 'hub.verify_token': token, 'hub.challenge': challenge } = req.query as any;
            const result = whatsappAdapter.verifyWebhook(mode, token, challenge);
            if (result) return reply.send(result);
            return reply.code(403).send('Verification failed');
        });

        app.post('/api/webhooks/whatsapp', async (req, reply) => {
            const sig = req.headers['x-hub-signature-256'] as string;
            const rawBody = JSON.stringify(req.body);
            if (sig && !whatsappAdapter.validateSignature(rawBody, sig)) {
                return reply.code(401).send('Invalid signature');
            }
            whatsappAdapter.handleWebhook(req.body);
            return reply.code(200).send('OK');
        });
    }

    // ── WebSocket ──
    const activeStreams = new Map<string, AbortController>();

    app.get('/ws', { websocket: true }, (socket) => {
        const handler = (event: string) => (data: any) => {
            try {
                socket.send(JSON.stringify({ type: event, data, timestamp: Date.now() }));
            } catch { }
        };

        const events = ['message:in', 'message:out', 'tool:call', 'tool:result', 'consent:request', 'consent:resolve', 'log', 'error'] as const;
        for (const ev of events) {
            bus.on(ev, handler(ev));
        }

        socket.on('message', async (raw) => {
            try {
                const msg = JSON.parse(raw.toString());
                if (msg.type === 'chat') {
                    const { streamChat } = await import('../gateway/router.js');
                    const sessionId = msg.sessionId || `webui_${Date.now()}`;

                    const controller = new AbortController();
                    activeStreams.set(sessionId, controller);

                    await streamChat(
                        {
                            id: `msg_${Date.now()}`,
                            sessionId,
                            platform: 'webui',
                            userId: sessionId, // Bypasses the single "admin" constraint, allowing multiple sessions
                            userName: 'Admin',
                            content: msg.text,
                            timestamp: Date.now(),
                        },
                        (token: string, done: boolean) => {
                            socket.send(JSON.stringify({ type: 'chat:stream', data: { token, done } }));
                        },
                        controller.signal
                    );

                    activeStreams.delete(sessionId);
                } else if (msg.type === 'stop') {
                    const sessionId = msg.sessionId;
                    if (sessionId && activeStreams.has(sessionId)) {
                        activeStreams.get(sessionId)?.abort();
                        activeStreams.delete(sessionId);
                        log('info', 'api', `Stream aborted by user for session ${sessionId}`);
                    }
                }
            } catch (err) {
                log('error', 'api', `WS message error: ${err}`);
            }
        });

        socket.on('close', () => {
            for (const ev of events) {
                bus.removeListener(ev, handler(ev));
            }
        });
    });

    // ── SPA fallback ──
    app.setNotFoundHandler(async (req, reply) => {
        if (req.url.startsWith('/api/')) return reply.code(404).send({ error: 'Not found' });
        return reply.sendFile('index.html');
    });

    // ── Log events to DB ──
    bus.onEvent('log', (data) => addLog(data.level, data.source, data.message, data.data));
    bus.onEvent('error', (data) => addLog('error', data.source, data.error));

    await app.listen({ port: cfg.server.port, host: cfg.server.host });
    log('info', 'api', `Server listening on http://${cfg.server.host}:${cfg.server.port}`);
}
