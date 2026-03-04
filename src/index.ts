// ═══════════════════════════════════════════════════
// Agent-02 — Main Entry Point & CLI
// ═══════════════════════════════════════════════════

import { loadConfig } from './config.js';
import { initDb, addLog } from './db.js';
import { initRouter } from './gateway/router.js';
import { log } from './gateway/eventbus.js';
import { startApiServer } from './api/server.js';
import { registerFilesystemSkills } from './skills/filesystem.js';
import { registerWebSkills } from './skills/web.js';
import { registerShellSkill } from './skills/shell.js';
import { TelegramAdapter } from './adapters/telegram.js';
import { DiscordAdapter } from './adapters/discord.js';
import { WhatsAppCloudAdapter } from './adapters/whatsapp_cloud.js';

async function main(): Promise<void> {
    console.log('');
    console.log('  ⚡ Agent-02 — Self-Hosted AI Gateway (Secure Edition)');
    console.log('  ════════════════════════════════════════');
    console.log('');

    // Initialize database (async sql.js)
    await initDb();

    // Load config
    const cfg = loadConfig();
    addLog('info', 'system', 'Agent-02 starting...');
    addLog('info', 'system', `LLM: ${cfg.llm.provider || 'not configured'} | Model: ${cfg.llm.model || 'N/A'}`);

    // Register skills
    registerFilesystemSkills();
    registerWebSkills();
    registerShellSkill();
    log('info', 'skills', 'All skills registered');

    // Initialize message router
    initRouter();

    // Start connectors
    const adapters: any[] = [];
    let waAdapter: WhatsAppCloudAdapter | undefined;

    if (cfg.connectors.telegram?.enabled && cfg.connectors.telegram.token) {
        try {
            const tg = new TelegramAdapter(cfg.connectors.telegram.token);
            await tg.connect();
            adapters.push(tg);
        } catch (err: any) {
            log('error', 'telegram', `Failed to connect: ${err.message}`);
        }
    }

    if (cfg.connectors.discord?.enabled && cfg.connectors.discord.token) {
        try {
            const dc = new DiscordAdapter(cfg.connectors.discord.token);
            await dc.connect();
            adapters.push(dc);
        } catch (err: any) {
            log('error', 'discord', `Failed to connect: ${err.message}`);
        }
    }

    if (cfg.connectors.whatsapp?.enabled && cfg.connectors.whatsapp.accessToken) {
        try {
            waAdapter = new WhatsAppCloudAdapter({
                phoneNumberId: cfg.connectors.whatsapp.phoneNumberId || '',
                accessToken: cfg.connectors.whatsapp.accessToken || '',
                appSecret: cfg.connectors.whatsapp.appSecret || '',
                verifyToken: cfg.connectors.whatsapp.verifyToken || 'agent02verify',
            });
            await waAdapter.connect();
            adapters.push(waAdapter);
        } catch (err: any) {
            log('error', 'whatsapp', `Failed to initialize: ${err.message}`);
        }
    }

    // Start API server
    await startApiServer(waAdapter);

    console.log('');
    console.log(`  🌐 Control UI:  http://localhost:${cfg.server.port}`);
    console.log(`  📡 API:         http://localhost:${cfg.server.port}/api/status`);
    console.log(`  🔌 WebSocket:   ws://localhost:${cfg.server.port}/ws`);
    console.log('');
    console.log('  ════════════════════════════════════════');
    console.log('  ⚡ Agent-02 is LIVE. Ctrl+C to stop.');
    console.log('');

    // Graceful shutdown
    const shutdown = async () => {
        console.log('  Shutting down...');
        for (const a of adapters) {
            try { await a.disconnect(); } catch { }
        }
        process.exit(0);
    };

    process.on('SIGINT', shutdown);
    process.on('SIGTERM', shutdown);
}

main().catch((err) => {
    console.error('Fatal error:', err);
    process.exit(1);
});
