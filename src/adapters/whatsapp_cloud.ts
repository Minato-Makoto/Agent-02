// ═══════════════════════════════════════════════════
// Agent-02 — WhatsApp Business Cloud API Adapter
// Official Meta Graph API — NO web-scraping
// ═══════════════════════════════════════════════════

import { BaseAdapter } from './base.js';
import { log } from '../gateway/eventbus.js';
import * as crypto from 'crypto';

const GRAPH_API = 'https://graph.facebook.com/v21.0';

export class WhatsAppCloudAdapter extends BaseAdapter {
    readonly platform = 'whatsapp';
    private phoneNumberId: string;
    private accessToken: string;
    private appSecret: string;
    private verifyToken: string;

    constructor(config: { phoneNumberId: string; accessToken: string; appSecret: string; verifyToken: string }) {
        super();
        this.phoneNumberId = config.phoneNumberId;
        this.accessToken = config.accessToken;
        this.appSecret = config.appSecret;
        this.verifyToken = config.verifyToken;
    }

    async connect(): Promise<void> {
        this.setupOutbound();
        log('info', 'whatsapp', 'WhatsApp Business Cloud API adapter ready (webhook mode)');
        log('info', 'whatsapp', `Configure webhook URL: https://your-domain/api/webhooks/whatsapp`);
    }

    async disconnect(): Promise<void> {
        log('info', 'whatsapp', 'Adapter stopped');
    }

    // ── Webhook Verification (GET) ──
    verifyWebhook(mode: string, token: string, challenge: string): string | null {
        if (mode === 'subscribe' && token === this.verifyToken) {
            log('info', 'whatsapp', 'Webhook verified successfully');
            return challenge;
        }
        log('warn', 'whatsapp', 'Webhook verification failed');
        return null;
    }

    // ── Webhook Signature Validation ──
    validateSignature(payload: string, signature: string): boolean {
        const expected = crypto
            .createHmac('sha256', this.appSecret)
            .update(payload)
            .digest('hex');
        return `sha256=${expected}` === signature;
    }

    // ── Incoming Webhook (POST) ──
    handleWebhook(body: any): void {
        try {
            const entries = body?.entry || [];
            for (const entry of entries) {
                const changes = entry?.changes || [];
                for (const change of changes) {
                    if (change.field !== 'messages') continue;
                    const value = change.value;
                    const messages = value?.messages || [];
                    const contacts = value?.contacts || [];

                    for (const msg of messages) {
                        const from = msg.from; // phone number
                        const contact = contacts.find((c: any) => c.wa_id === from);
                        const name = contact?.profile?.name || from;

                        let content = '';
                        if (msg.type === 'text') {
                            content = msg.text?.body || '';
                        } else {
                            content = `[${msg.type} message - not supported yet]`;
                        }

                        if (content) {
                            this.emitInbound(from, name, content);
                        }
                    }
                }
            }
        } catch (err: any) {
            log('error', 'whatsapp', `Webhook parse error: ${err.message}`);
        }
    }

    // ── Send Message via Cloud API ──
    async sendMessage(to: string, content: string): Promise<void> {
        const url = `${GRAPH_API}/${this.phoneNumberId}/messages`;

        const res = await fetch(url, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${this.accessToken}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                messaging_product: 'whatsapp',
                recipient_type: 'individual',
                to,
                type: 'text',
                text: { preview_url: false, body: content.slice(0, 4096) },
            }),
        });

        if (!res.ok) {
            const err = await res.text();
            log('error', 'whatsapp', `Send failed: ${err}`);
            throw new Error(`WhatsApp send failed: ${res.status}`);
        }
    }
}
