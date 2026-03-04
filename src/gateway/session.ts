// ═══════════════════════════════════════════════════
// Agent-02 — Session Manager
// ═══════════════════════════════════════════════════

import { getOrCreateSession, getHistory, saveMessage } from '../db.js';

export interface ChatMessage {
    role: 'system' | 'user' | 'assistant' | 'tool';
    content: string;
    tool_calls?: any;
    tool_call_id?: string;
}

export class SessionManager {
    getOrCreate(platform: string, userId: string, displayName = ''): string {
        return getOrCreateSession(platform, userId, displayName);
    }

    hydrate(sessionId: string, limit = 30): ChatMessage[] {
        const rows = getHistory(sessionId, limit);
        return rows.map((r: any) => ({
            role: r.role as ChatMessage['role'],
            content: r.content,
            ...(r.tool_calls ? { tool_calls: JSON.parse(r.tool_calls) } : {}),
            ...(r.tool_call_id ? { tool_call_id: r.tool_call_id } : {}),
        }));
    }

    save(sessionId: string, role: string, content: string, toolCalls?: any, toolCallId?: string): void {
        saveMessage(sessionId, role, content, toolCalls, toolCallId);
    }
}

export const sessions = new SessionManager();
