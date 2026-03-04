// ═══════════════════════════════════════════════════
// Agent-02 — Telegram Adapter (Official Bot API)
// ═══════════════════════════════════════════════════

import { Telegraf } from 'telegraf';
import { BaseAdapter } from './base.js';
import { log } from '../gateway/eventbus.js';

export class TelegramAdapter extends BaseAdapter {
    readonly platform = 'telegram';
    private bot: Telegraf;
    private chatMap = new Map<string, number>();

    constructor(token: string) {
        super();
        this.bot = new Telegraf(token);
    }

    async connect(): Promise<void> {
        this.bot.on('message', (ctx) => {
            const msg = ctx.message;
            const userId = String(msg.from?.id || '');
            const userName = msg.from?.first_name || msg.from?.username || 'Unknown';
            let content = '';

            if ('text' in msg) content = msg.text;
            else if ('caption' in msg && msg.caption) content = `[Media] ${msg.caption}`;
            else content = '[Unsupported message type]';

            if (!content.trim()) return;

            this.chatMap.set(userId, msg.chat.id);
            this.emitInbound(userId, userName, content);
        });

        this.setupOutbound();

        await this.bot.launch();
        log('info', 'telegram', 'Bot connected via Official Bot API');
    }

    async disconnect(): Promise<void> {
        this.bot.stop();
        log('info', 'telegram', 'Bot disconnected');
    }

    async sendMessage(userId: string, content: string): Promise<void> {
        const chatId = this.chatMap.get(userId);
        if (!chatId) {
            log('warn', 'telegram', `No chat ID for user ${userId}`);
            return;
        }

        // Split long messages (Telegram limit: 4096 chars)
        const chunks = splitMessage(content, 4000);
        for (const chunk of chunks) {
            await this.bot.telegram.sendMessage(chatId, chunk, { parse_mode: 'Markdown' }).catch(() => {
                // Retry without Markdown if parsing fails
                return this.bot.telegram.sendMessage(chatId, chunk);
            });
        }
    }
}

function splitMessage(text: string, maxLen: number): string[] {
    if (text.length <= maxLen) return [text];
    const chunks: string[] = [];
    for (let i = 0; i < text.length; i += maxLen) {
        chunks.push(text.slice(i, i + maxLen));
    }
    return chunks;
}
