// ═══════════════════════════════════════════════════
// Agent-02 — Base Adapter Interface
// ═══════════════════════════════════════════════════

import { bus, log, type AgentMessage } from '../gateway/eventbus.js';
import * as crypto from 'crypto';

export abstract class BaseAdapter {
    abstract readonly platform: string;

    abstract connect(): Promise<void>;
    abstract disconnect(): Promise<void>;
    abstract sendMessage(userId: string, content: string): Promise<void>;

    protected emitInbound(userId: string, userName: string, content: string): void {
        const msg: AgentMessage = {
            id: crypto.randomUUID(),
            sessionId: '',
            platform: this.platform,
            userId,
            userName,
            content,
            timestamp: Date.now(),
        };
        bus.emitEvent('message:in', msg);
        log('info', this.platform, `Message from ${userName}: ${content.slice(0, 80)}`);
    }

    protected setupOutbound(): void {
        bus.onEvent('message:out', async (res) => {
            if (res.platform !== this.platform) return;
            try {
                // Extract userId from sessionId (format: platform_userId_timestamp)
                const parts = res.sessionId.split('_');
                const userId = parts.slice(1, -1).join('_');
                await this.sendMessage(userId, res.content);
            } catch (err: any) {
                log('error', this.platform, `Send failed: ${err.message}`);
            }
        });
    }
}
