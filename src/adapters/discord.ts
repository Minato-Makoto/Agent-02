// ═══════════════════════════════════════════════════
// Agent-02 — Discord Adapter (Official Bot API)
// ═══════════════════════════════════════════════════

import { Client, GatewayIntentBits, type Message } from 'discord.js';
import { BaseAdapter } from './base.js';
import { log } from '../gateway/eventbus.js';

export class DiscordAdapter extends BaseAdapter {
    readonly platform = 'discord';
    private client: Client;
    private token: string;
    private channelMap = new Map<string, string>(); // userId -> channelId

    constructor(token: string) {
        super();
        this.token = token;
        this.client = new Client({
            intents: [
                GatewayIntentBits.Guilds,
                GatewayIntentBits.GuildMessages,
                GatewayIntentBits.DirectMessages,
                GatewayIntentBits.MessageContent,
            ],
        });
    }

    async connect(): Promise<void> {
        this.client.on('messageCreate', (msg: Message) => {
            if (msg.author.bot) return;
            const userId = msg.author.id;
            const userName = msg.author.displayName || msg.author.username;
            this.channelMap.set(userId, msg.channelId);
            this.emitInbound(userId, userName, msg.content);
        });

        this.client.on('ready', () => {
            log('info', 'discord', `Bot connected as ${this.client.user?.tag}`);
        });

        this.setupOutbound();
        await this.client.login(this.token);
    }

    async disconnect(): Promise<void> {
        await this.client.destroy();
        log('info', 'discord', 'Bot disconnected');
    }

    async sendMessage(userId: string, content: string): Promise<void> {
        const channelId = this.channelMap.get(userId);
        if (!channelId) return;

        const channel = await this.client.channels.fetch(channelId);
        if (!channel?.isTextBased() || !('send' in channel)) return;

        // Discord limit: 2000 chars
        const chunks = content.length > 1900 ? splitMsg(content, 1900) : [content];
        for (const chunk of chunks) {
            await (channel as any).send(chunk);
        }
    }
}

function splitMsg(text: string, max: number): string[] {
    const out: string[] = [];
    for (let i = 0; i < text.length; i += max) out.push(text.slice(i, i + max));
    return out;
}
