// ═══════════════════════════════════════════════════
// Agent-02 — Event Bus (typed EventEmitter)
// ═══════════════════════════════════════════════════

import { EventEmitter } from 'events';

export interface AgentMessage {
    id: string;
    sessionId: string;
    platform: string;
    userId: string;
    userName: string;
    content: string;
    timestamp: number;
}

export interface AgentResponse {
    sessionId: string;
    platform: string;
    content: string;
    toolCalls?: ToolCallRequest[];
}

export interface ToolCallRequest {
    id: string;
    name: string;
    args: Record<string, any>;
}

export interface ConsentEvent {
    consentId: string;
    sessionId: string;
    skillName: string;
    args: Record<string, any>;
    status: 'pending' | 'approved' | 'denied';
}

export type BusEvents = {
    'message:in': AgentMessage;
    'message:out': AgentResponse;
    'tool:call': ToolCallRequest & { sessionId: string };
    'tool:result': { sessionId: string; toolCallId: string; result: string };
    'consent:request': ConsentEvent;
    'consent:resolve': ConsentEvent;
    'log': { level: string; source: string; message: string; data?: any };
    'error': { source: string; error: string };
};

class TypedEventBus extends EventEmitter {
    emitEvent<K extends keyof BusEvents>(event: K, data: BusEvents[K]): void {
        this.emit(event, data);
    }
    onEvent<K extends keyof BusEvents>(event: K, handler: (data: BusEvents[K]) => void): void {
        this.on(event, handler);
    }
}

export const bus = new TypedEventBus();
bus.setMaxListeners(50);

// Convenience logger
export function log(level: string, source: string, message: string, data?: any): void {
    bus.emitEvent('log', { level, source, message, data });
}
