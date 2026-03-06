import fastifyStatic from '@fastify/static';
import fastifyWebsocket from '@fastify/websocket';
import Fastify from 'fastify';
import { APP_VERSION } from '../constants.js';
import { getSystemPrompt, loadConfig, saveConfig, type AppConfig, type ConnectorConfig } from '../config.js';
import { addLog, getAllSessions, getHistory, getPendingConsents, getRecentLogs } from '../db.js';
import { bus, log } from '../gateway/eventbus.js';
import { resolveConsentRequest, streamChat } from '../gateway/router.js';
import { discoverLocalModels } from '../runtime/local_models.js';
import { freePortIfOccupied } from '../runtime/ports.js';
import { LLAMA_CPP_DIR, LLAMA_SERVER_CANDIDATES, MODELS_DIR, UI_DIST_DIR } from '../paths.js';
import { resetProvider, shutdownProvider } from '../llm/provider.js';
import { WhatsAppCloudAdapter } from '../adapters/whatsapp_cloud.js';
import type { FastifyInstance } from 'fastify';

function maskSecret(value: string, visibleTail = 4): string {
  if (!value) return '';
  if (value.length <= visibleTail) return '*'.repeat(Math.max(4, value.length));
  return `${'*'.repeat(Math.max(4, value.length - visibleTail))}${value.slice(-visibleTail)}`;
}

function toUiConnector(config: ConnectorConfig) {
  return {
    enabled: config.enabled,
    tokenMasked: maskSecret(config.token),
    phoneNumberId: config.phoneNumberId,
    accessTokenMasked: maskSecret(config.accessToken),
    verifyTokenMasked: maskSecret(config.verifyToken),
    appSecretMasked: maskSecret(config.appSecret),
  };
}

function toUiConfig(config: AppConfig) {
  return {
    version: APP_VERSION,
    llm: {
      provider: config.llm.provider,
      model: config.llm.model,
      baseUrl: config.llm.baseUrl,
      apiKeyMasked: maskSecret(config.llm.apiKey),
      ggufPath: config.llm.ggufPath,
      systemPrompt: getSystemPrompt(),
      requestTimeoutSec: config.llm.requestTimeoutSec,
      maxTokens: config.llm.maxTokens,
      temperature: config.llm.temperature,
    },
    connectors: {
      telegram: toUiConnector(config.connectors.telegram),
      discord: toUiConnector(config.connectors.discord),
      whatsapp: toUiConnector(config.connectors.whatsapp),
    },
    skills: {
      filesystemEnabled: config.skills.filesystem.enabled,
      webEnabled: config.skills.web.enabled,
      shellEnabled: config.skills.shell.enabled,
      shellRequiresConsent: config.skills.shell.requiresConsent,
    },
    security: {
      allowedWorkDir: config.security.allowedWorkDir,
      consentRequired: config.security.consentRequired,
    },
  };
}

function buildConfigPatch(payload: any): Partial<AppConfig> {
  const patch: Partial<AppConfig> = {};

  if (payload?.llm) {
    patch.llm = {} as AppConfig['llm'];
    if (typeof payload.llm.provider === 'string') patch.llm.provider = payload.llm.provider;
    if (typeof payload.llm.model === 'string') patch.llm.model = payload.llm.model;
    if (typeof payload.llm.baseUrl === 'string') patch.llm.baseUrl = payload.llm.baseUrl;
    if (typeof payload.llm.apiKey === 'string') patch.llm.apiKey = payload.llm.apiKey;
    if (typeof payload.llm.ggufPath === 'string') patch.llm.ggufPath = payload.llm.ggufPath;
    if (typeof payload.llm.systemPrompt === 'string') patch.llm.systemPrompt = payload.llm.systemPrompt;
    if (typeof payload.llm.requestTimeoutSec === 'number') patch.llm.requestTimeoutSec = payload.llm.requestTimeoutSec;
    if (typeof payload.llm.maxTokens === 'number') patch.llm.maxTokens = payload.llm.maxTokens;
    if (typeof payload.llm.temperature === 'number') patch.llm.temperature = payload.llm.temperature;
  }

  if (payload?.connectors) {
    patch.connectors = {} as AppConfig['connectors'];
    for (const connectorName of ['telegram', 'discord', 'whatsapp'] as const) {
      const rawConnector = payload.connectors[connectorName];
      if (!rawConnector) continue;

      patch.connectors[connectorName] = {} as ConnectorConfig;
      if (typeof rawConnector.enabled === 'boolean') patch.connectors[connectorName].enabled = rawConnector.enabled;
      if (typeof rawConnector.token === 'string') patch.connectors[connectorName].token = rawConnector.token;
      if (typeof rawConnector.phoneNumberId === 'string') patch.connectors[connectorName].phoneNumberId = rawConnector.phoneNumberId;
      if (typeof rawConnector.accessToken === 'string') patch.connectors[connectorName].accessToken = rawConnector.accessToken;
      if (typeof rawConnector.verifyToken === 'string') patch.connectors[connectorName].verifyToken = rawConnector.verifyToken;
      if (typeof rawConnector.appSecret === 'string') patch.connectors[connectorName].appSecret = rawConnector.appSecret;
    }
  }

  if (payload?.skills) {
    patch.skills = {} as AppConfig['skills'];

    const shellEnabled = typeof payload.skills.shellEnabled === 'boolean'
      ? payload.skills.shellEnabled
      : typeof payload.skills.shell === 'boolean'
        ? payload.skills.shell
        : undefined;

    if (typeof payload.skills.filesystemEnabled === 'boolean') {
      patch.skills.filesystem = {
        enabled: payload.skills.filesystemEnabled,
        requiresConsent: false,
      };
    }

    if (typeof payload.skills.webEnabled === 'boolean') {
      patch.skills.web = {
        enabled: payload.skills.webEnabled,
        requiresConsent: false,
      };
    }

    if (typeof shellEnabled === 'boolean') {
      patch.skills.shell = {
        enabled: shellEnabled,
        requiresConsent: true,
      };
    }
  }

  if (payload?.security) {
    patch.security = {} as AppConfig['security'];
    if (typeof payload.security.allowedWorkDir === 'string') patch.security.allowedWorkDir = payload.security.allowedWorkDir;
    if (typeof payload.security.consentRequired === 'boolean') patch.security.consentRequired = payload.security.consentRequired;
  }

  return patch;
}

export interface ApiServerHandle {
  app: FastifyInstance;
  close: () => Promise<void>;
}

export async function startApiServer(whatsappAdapter?: WhatsAppCloudAdapter): Promise<ApiServerHandle> {
  const cfg = loadConfig();
  const app = Fastify({
    logger: false,
    bodyLimit: 1024 * 1024,
  });

  await app.register(fastifyWebsocket);

  try {
    await app.register(fastifyStatic, { root: UI_DIST_DIR, prefix: '/' });
  } catch {
    log('warn', 'api', `UI not built at ${UI_DIST_DIR}.`);
  }

  app.get('/api/status', async () => {
    const localModels = await discoverLocalModels(20);
    const current = loadConfig();

    return {
      status: 'running',
      version: APP_VERSION,
      uptime: process.uptime(),
      memory: process.memoryUsage(),
      llm: {
        provider: current.llm.provider,
        model: current.llm.model,
      },
      runtime: {
        workspace: current.security.allowedWorkDir,
        llamaCppDir: LLAMA_CPP_DIR,
        modelsDir: MODELS_DIR,
        localModelCount: localModels.length,
      },
    };
  });

  app.get('/api/runtime', async () => ({
    llamaCppDir: LLAMA_CPP_DIR,
    llamaServerCandidates: LLAMA_SERVER_CANDIDATES,
    modelsDir: MODELS_DIR,
    localModels: await discoverLocalModels(),
    systemPromptPath: 'data/instructions/system.md',
  }));

  app.get('/api/config', async () => toUiConfig(loadConfig()));

  app.post('/api/config', async (req) => {
    const patch = buildConfigPatch(req.body);
    await shutdownProvider();
    const next = saveConfig(patch);
    resetProvider();
    return { ok: true, config: toUiConfig(next) };
  });

  app.get('/api/sessions', async () =>
    getAllSessions().map((row: any) => ({
      id: row.id,
      platform: row.platform,
      userId: row.platform_uid,
      displayName: row.display_name,
      createdAt: row.created_at,
      updatedAt: row.updated_at,
      messageCount: Number(row.message_count || 0),
    })),
  );

  app.get('/api/sessions/:id/messages', async (req) => {
    const { id } = req.params as { id: string };
    return getHistory(id, 100).map((row: any) => ({
      role: row.role,
      content: row.content,
      toolCalls: row.tool_calls ? JSON.parse(row.tool_calls) : undefined,
      toolCallId: row.tool_call_id || undefined,
    }));
  });

  app.get('/api/logs', async (req) => {
    const query = req.query as { limit?: string };
    return getRecentLogs(Number(query.limit) || 100);
  });

  app.get('/api/consents', async () =>
    getPendingConsents().map((row: any) => ({
      id: row.id,
      sessionId: row.session_id,
      skillName: row.skill_name,
      args: (() => {
        try {
          return JSON.parse(row.args);
        } catch {
          return {};
        }
      })(),
      createdAt: row.created_at,
    })),
  );

  app.post('/api/consents/:id', async (req) => {
    const { id } = req.params as { id: string };
    const body = (req.body ?? {}) as { approved?: boolean };
    resolveConsentRequest(id, body.approved === true);
    return { ok: true };
  });

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

  app.get('/ws', { websocket: true }, (socket) => {
    const listeners = new Map<string, (data: any) => void>();
    const activeStreams = new Map<string, AbortController>();

    for (const eventName of ['message:in', 'message:out', 'tool:call', 'tool:result', 'consent:request', 'consent:resolve', 'log', 'error'] as const) {
      const handler = (data: any) => {
        try {
          socket.send(JSON.stringify({ type: eventName, data, timestamp: Date.now() }));
        } catch {
          // Ignore socket errors; close handler below will clean up listeners.
        }
      };

      listeners.set(eventName, handler);
      bus.on(eventName, handler);
    }

    socket.on('message', async (raw) => {
      try {
        const msg = JSON.parse(raw.toString());
        if (msg.type === 'chat') {
          const sessionId = msg.sessionId || `webui_${Date.now()}`;
          const controller = new AbortController();
          activeStreams.set(sessionId, controller);

          await streamChat(
            {
              id: `msg_${Date.now()}`,
              sessionId,
              platform: 'webui',
              userId: sessionId,
              userName: 'Web User',
              content: String(msg.text || ''),
              timestamp: Date.now(),
            },
            (event) => {
              socket.send(JSON.stringify({ type: 'chat:stream', data: { sessionId, ...event } }));
            },
            controller.signal,
          );

          activeStreams.delete(sessionId);
        }

        if (msg.type === 'stop') {
          const sessionId = String(msg.sessionId || '');
          activeStreams.get(sessionId)?.abort();
          activeStreams.delete(sessionId);
        }
      } catch (err: any) {
        log('error', 'api', `WS message error: ${err.message}`);
        try {
          socket.send(JSON.stringify({ type: 'chat:error', error: err.message }));
        } catch {
          // Ignore send failures on broken sockets.
        }
      }
    });

    socket.on('close', () => {
      for (const controller of activeStreams.values()) {
        controller.abort();
      }

      for (const [eventName, handler] of listeners.entries()) {
        bus.removeListener(eventName, handler);
      }
    });
  });

  app.setNotFoundHandler(async (req, reply) => {
    if (req.url.startsWith('/api/')) {
      return reply.code(404).send({ error: 'Not found' });
    }

    return reply.sendFile('index.html');
  });

  bus.onEvent('log', (data) => addLog(data.level, data.source, data.message, data.data));
  bus.onEvent('error', (data) => addLog('error', data.source, data.error));

  const killedPids = await freePortIfOccupied(cfg.server.port);
  if (killedPids.length > 0) {
    log('warn', 'api', `Port ${cfg.server.port} was busy. Stopped process(es): ${killedPids.join(', ')}`);
  }
  await app.listen({ port: cfg.server.port, host: cfg.server.host });
  log('info', 'api', `Server listening on http://${cfg.server.host}:${cfg.server.port}`);
  return {
    app,
    close: async () => {
      await app.close();
    },
  };
}
