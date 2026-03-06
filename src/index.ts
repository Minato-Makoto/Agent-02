import { DiscordAdapter } from './adapters/discord.js';
import { TelegramAdapter } from './adapters/telegram.js';
import { WhatsAppCloudAdapter } from './adapters/whatsapp_cloud.js';
import { startApiServer } from './api/server.js';
import { APP_NAME, APP_VERSION } from './constants.js';
import { loadConfig } from './config.js';
import { addLog, initDb } from './db.js';
import { log } from './gateway/eventbus.js';
import { initRouter } from './gateway/router.js';
import { shutdownProvider } from './llm/provider.js';
import { registerFilesystemSkills } from './skills/filesystem.js';
import { registerShellSkill } from './skills/shell.js';
import { registerWebSkills } from './skills/web.js';

async function main(): Promise<void> {
  console.log('');
  console.log(`  ${APP_NAME} v${APP_VERSION}`);
  console.log('  Private AI gateway with local-first safety controls');
  console.log('');

  await initDb();

  const cfg = loadConfig();
  addLog('info', 'system', `${APP_NAME} v${APP_VERSION} starting`);
  addLog('info', 'system', `LLM provider: ${cfg.llm.provider || 'not configured'} | Model: ${cfg.llm.model || 'N/A'}`);

  registerFilesystemSkills();
  registerWebSkills();
  registerShellSkill();
  initRouter();

  const adapters: Array<{ disconnect: () => Promise<void> }> = [];
  let apiServer: Awaited<ReturnType<typeof startApiServer>> | null = null;
  let whatsappAdapter: WhatsAppCloudAdapter | undefined;

  if (cfg.connectors.telegram.enabled && cfg.connectors.telegram.token) {
    try {
      const adapter = new TelegramAdapter(cfg.connectors.telegram.token);
      await adapter.connect();
      adapters.push(adapter);
    } catch (err: any) {
      log('error', 'telegram', `Failed to connect: ${err.message}`);
    }
  }

  if (cfg.connectors.discord.enabled && cfg.connectors.discord.token) {
    try {
      const adapter = new DiscordAdapter(cfg.connectors.discord.token);
      await adapter.connect();
      adapters.push(adapter);
    } catch (err: any) {
      log('error', 'discord', `Failed to connect: ${err.message}`);
    }
  }

  if (cfg.connectors.whatsapp.enabled && cfg.connectors.whatsapp.accessToken) {
    try {
      whatsappAdapter = new WhatsAppCloudAdapter({
        phoneNumberId: cfg.connectors.whatsapp.phoneNumberId,
        accessToken: cfg.connectors.whatsapp.accessToken,
        appSecret: cfg.connectors.whatsapp.appSecret,
        verifyToken: cfg.connectors.whatsapp.verifyToken,
      });
      await whatsappAdapter.connect();
      adapters.push(whatsappAdapter);
    } catch (err: any) {
      log('error', 'whatsapp', `Failed to initialize: ${err.message}`);
    }
  }

  apiServer = await startApiServer(whatsappAdapter);

  console.log(`  Control panel: http://localhost:${cfg.server.port}`);
  console.log(`  API status:    http://localhost:${cfg.server.port}/api/status`);
  console.log(`  WebSocket:     ws://localhost:${cfg.server.port}/ws`);
  console.log('');

  let shuttingDown = false;
  const shutdown = async (reason = 'shutdown', exitCode = 0) => {
    if (shuttingDown) {
      return;
    }
    shuttingDown = true;

    console.log(`  Shutting down (${reason})...`);
    for (const adapter of adapters) {
      try {
        await adapter.disconnect();
      } catch {
        // Ignore adapter shutdown failures.
      }
    }

    try {
      await apiServer?.close();
    } catch {
      // Ignore API server shutdown failures.
    }

    await shutdownProvider();
    process.exit(exitCode);
  };

  process.once('SIGINT', () => void shutdown('SIGINT'));
  process.once('SIGTERM', () => void shutdown('SIGTERM'));
  process.once('SIGBREAK', () => void shutdown('SIGBREAK'));
  process.once('SIGHUP', () => void shutdown('SIGHUP'));
  process.once('disconnect', () => void shutdown('disconnect'));
  process.once('exit', () => {
    void shutdownProvider();
  });
  process.once('uncaughtException', (err) => {
    console.error('Uncaught exception:', err);
    void shutdown('uncaughtException', 1);
  });
  process.once('unhandledRejection', (reason) => {
    console.error('Unhandled rejection:', reason);
    void shutdown('unhandledRejection', 1);
  });
}

main().catch((err) => {
  console.error('Fatal error:', err);
  void shutdownProvider();
  process.exit(1);
});
