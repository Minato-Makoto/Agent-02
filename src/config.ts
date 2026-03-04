// ═══════════════════════════════════════════════════
// Agent-02 — Secure Config Manager
// ═══════════════════════════════════════════════════

import * as fs from 'fs';
import * as path from 'path';
import * as crypto from 'crypto';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DATA_DIR = path.join(__dirname, '..', 'data');
const CONFIG_PATH = path.join(DATA_DIR, 'config.json');
const SECRET_KEY_PATH = path.join(DATA_DIR, '.secret_key');

export interface LLMConfig {
    provider: string;
    apiKey: string;
    model: string;
    baseUrl?: string;
    ggufPath?: string;
}

export interface ConnectorConfig {
    enabled: boolean;
    token?: string;
    // WhatsApp Business Cloud API fields
    phoneNumberId?: string;
    accessToken?: string;
    verifyToken?: string;
    appSecret?: string;
}

export interface SkillConfig {
    enabled: boolean;
    requiresConsent: boolean;
    allowedPaths?: string[];  // filesystem jail
}

export interface AppConfig {
    llm: LLMConfig;
    server: { port: number; host: string };
    connectors: Record<string, ConnectorConfig>;
    skills: Record<string, SkillConfig>;
    security: {
        encryptSecrets: boolean;
        consentRequired: boolean;
        allowedWorkDir: string;
    };
}

const DEFAULT_CONFIG: AppConfig = {
    llm: { provider: '', apiKey: '', model: '' },
    server: { port: 8080, host: '0.0.0.0' },
    connectors: {
        telegram: { enabled: false },
        discord: { enabled: false },
        whatsapp: { enabled: false },
    },
    skills: {
        filesystem: { enabled: true, requiresConsent: false, allowedPaths: [] },
        web: { enabled: true, requiresConsent: false },
        shell: { enabled: false, requiresConsent: true },
    },
    security: {
        encryptSecrets: true,
        consentRequired: true,
        allowedWorkDir: path.join(DATA_DIR, 'workspace'),
    },
};

// ── Encryption helpers ──

function getOrCreateKey(): Buffer {
    if (fs.existsSync(SECRET_KEY_PATH)) {
        return Buffer.from(fs.readFileSync(SECRET_KEY_PATH, 'utf8'), 'hex');
    }
    const key = crypto.randomBytes(32);
    if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });
    fs.writeFileSync(SECRET_KEY_PATH, key.toString('hex'), { mode: 0o600 });
    return key;
}

function encrypt(text: string): string {
    if (!text) return '';
    const key = getOrCreateKey();
    const iv = crypto.randomBytes(16);
    const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
    const encrypted = Buffer.concat([cipher.update(text, 'utf8'), cipher.final()]);
    const tag = cipher.getAuthTag();
    return `${iv.toString('hex')}:${tag.toString('hex')}:${encrypted.toString('hex')}`;
}

function decrypt(encoded: string): string {
    if (!encoded || !encoded.includes(':')) return encoded;
    try {
        const [ivHex, tagHex, dataHex] = encoded.split(':');
        const key = getOrCreateKey();
        const decipher = crypto.createDecipheriv('aes-256-gcm', key, Buffer.from(ivHex, 'hex'));
        decipher.setAuthTag(Buffer.from(tagHex, 'hex'));
        return decipher.update(Buffer.from(dataHex, 'hex'), undefined, 'utf8') + decipher.final('utf8');
    } catch {
        return encoded; // fallback: treat as plaintext
    }
}

// ── Config I/O ──

let _config: AppConfig | null = null;

export function loadConfig(): AppConfig {
    if (_config) return _config;
    if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });

    if (fs.existsSync(CONFIG_PATH)) {
        const raw = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
        _config = deepMerge(DEFAULT_CONFIG, raw) as AppConfig;
        // Decrypt sensitive fields
        if (_config.llm.apiKey) _config.llm.apiKey = decrypt(_config.llm.apiKey);
        for (const [, conn] of Object.entries(_config.connectors)) {
            if (conn.token) conn.token = decrypt(conn.token);
            if (conn.accessToken) conn.accessToken = decrypt(conn.accessToken);
            if (conn.appSecret) conn.appSecret = decrypt(conn.appSecret);
        }
    } else {
        _config = structuredClone(DEFAULT_CONFIG);
    }
    return _config;
}

export function saveConfig(updates: Partial<AppConfig>): AppConfig {
    const current = loadConfig();
    const merged = deepMerge(current, updates) as AppConfig;

    // Encrypt before saving
    const toSave = structuredClone(merged);
    if (toSave.llm.apiKey) toSave.llm.apiKey = encrypt(toSave.llm.apiKey);
    for (const [, conn] of Object.entries(toSave.connectors)) {
        if (conn.token) conn.token = encrypt(conn.token);
        if (conn.accessToken) conn.accessToken = encrypt(conn.accessToken);
        if (conn.appSecret) conn.appSecret = encrypt(conn.appSecret);
    }

    fs.writeFileSync(CONFIG_PATH, JSON.stringify(toSave, null, 2), 'utf8');
    _config = merged;
    return _config;
}

export function resetConfigCache(): void {
    _config = null;
}

function deepMerge(target: any, source: any): any {
    const result = { ...target };
    for (const key of Object.keys(source)) {
        if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
            result[key] = deepMerge(target[key] || {}, source[key]);
        } else {
            result[key] = source[key];
        }
    }
    return result;
}
