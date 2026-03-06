import * as crypto from 'crypto';
import * as fs from 'fs';
import * as path from 'path';
import { CONFIG_PATH, DATA_DIR, SECRET_KEY_PATH, SYSTEM_PROMPT_PATH, WORKSPACE_DIR } from './paths.js';

export interface LLMConfig {
  provider: string;
  apiKey: string;
  model: string;
  baseUrl: string;
  ggufPath: string;
  systemPrompt: string;
  requestTimeoutSec: number;
  maxTokens: number;
  temperature: number;
}

export interface ConnectorConfig {
  enabled: boolean;
  token: string;
  phoneNumberId: string;
  accessToken: string;
  verifyToken: string;
  appSecret: string;
}

export interface SkillConfig {
  enabled: boolean;
  requiresConsent: boolean;
  allowedPaths?: string[];
}

export interface AppConfig {
  llm: LLMConfig;
  server: {
    port: number;
    host: string;
  };
  connectors: {
    telegram: ConnectorConfig;
    discord: ConnectorConfig;
    whatsapp: ConnectorConfig;
  };
  skills: {
    filesystem: SkillConfig;
    web: SkillConfig;
    shell: SkillConfig;
  };
  security: {
    encryptSecrets: boolean;
    consentRequired: boolean;
    allowedWorkDir: string;
  };
}

const DEFAULT_SYSTEM_PROMPT = `You are Agent-02, a helpful AI assistant running as a self-hosted gateway.
You have access to tools that the user has explicitly enabled. Before executing any potentially dangerous action, you will ask for confirmation.
Always be helpful, concise, and security-conscious. Never expose internal system details like API keys or file paths outside the allowed workspace.`;

const DEFAULT_CONFIG: AppConfig = {
  llm: {
    provider: '',
    apiKey: '',
    model: '',
    baseUrl: '',
    ggufPath: '',
    systemPrompt: DEFAULT_SYSTEM_PROMPT,
    requestTimeoutSec: 45,
    maxTokens: 800,
    temperature: 0.2,
  },
  server: {
    port: 8420,
    host: '127.0.0.1',
  },
  connectors: {
    telegram: {
      enabled: false,
      token: '',
      phoneNumberId: '',
      accessToken: '',
      verifyToken: '',
      appSecret: '',
    },
    discord: {
      enabled: false,
      token: '',
      phoneNumberId: '',
      accessToken: '',
      verifyToken: '',
      appSecret: '',
    },
    whatsapp: {
      enabled: false,
      token: '',
      phoneNumberId: '',
      accessToken: '',
      verifyToken: 'agent02verify',
      appSecret: '',
    },
  },
  skills: {
    filesystem: { enabled: true, requiresConsent: false, allowedPaths: [] },
    web: { enabled: true, requiresConsent: false },
    shell: { enabled: false, requiresConsent: true },
  },
  security: {
    encryptSecrets: true,
    consentRequired: true,
    allowedWorkDir: WORKSPACE_DIR,
  },
};

let _config: AppConfig | null = null;
let _rawConfig: Record<string, any> | null = null;

function ensureDataDirs(): void {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  fs.mkdirSync(path.dirname(SYSTEM_PROMPT_PATH), { recursive: true });
}

function isPlainObject(value: unknown): value is Record<string, any> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function readText(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function readBool(value: unknown, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback;
}

function readNumber(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function readStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

function parseMasterKey(raw: string): Buffer {
  const trimmed = raw.trim();
  if (!trimmed) {
    throw new Error('Empty AGENT02_MASTER_KEY');
  }

  try {
    const decoded = Buffer.from(trimmed, 'base64');
    if (decoded.length === 32 && decoded.toString('base64') === trimmed.replace(/\s+/g, '')) {
      return decoded;
    }
  } catch {
    // Fall through to passphrase hashing below.
  }

  return crypto.createHash('sha256').update(trimmed, 'utf8').digest();
}

function getOrCreateKey(): Buffer {
  const envKey = process.env.AGENT02_MASTER_KEY;
  if (envKey) {
    return parseMasterKey(envKey);
  }

  if (fs.existsSync(SECRET_KEY_PATH)) {
    return Buffer.from(fs.readFileSync(SECRET_KEY_PATH, 'utf8'), 'hex');
  }

  const key = crypto.randomBytes(32);
  ensureDataDirs();
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
  if (!encoded || !encoded.includes(':')) {
    return encoded;
  }

  try {
    const [ivHex, tagHex, dataHex] = encoded.split(':');
    const key = getOrCreateKey();
    const decipher = crypto.createDecipheriv('aes-256-gcm', key, Buffer.from(ivHex, 'hex'));
    decipher.setAuthTag(Buffer.from(tagHex, 'hex'));
    return decipher.update(Buffer.from(dataHex, 'hex'), undefined, 'utf8') + decipher.final('utf8');
  } catch {
    return encoded;
  }
}

function readFirstSecret(...candidates: unknown[]): string {
  for (const candidate of candidates) {
    if (typeof candidate === 'string' && candidate.trim()) {
      return decrypt(candidate);
    }
  }

  return '';
}

function deepMerge<T>(target: T, source: unknown): T {
  if (!isPlainObject(source)) {
    return target;
  }

  const result: Record<string, any> = Array.isArray(target) ? [...(target as any[])] : { ...(target as Record<string, any>) };

  for (const [key, value] of Object.entries(source)) {
    if (isPlainObject(value) && isPlainObject(result[key])) {
      result[key] = deepMerge(result[key], value);
      continue;
    }

    result[key] = value;
  }

  return result as T;
}

function normalizeSkillConfig(value: unknown, fallback: SkillConfig): SkillConfig {
  if (typeof value === 'boolean') {
    return { ...fallback, enabled: value };
  }

  if (!isPlainObject(value)) {
    return { ...fallback };
  }

  return {
    enabled: readBool(value.enabled, fallback.enabled),
    requiresConsent: readBool(value.requiresConsent, fallback.requiresConsent),
    allowedPaths: readStringArray(value.allowedPaths),
  };
}

function normalizeConnectorConfig(rawConnector: unknown, fallback: ConnectorConfig): ConnectorConfig {
  if (!isPlainObject(rawConnector)) {
    return { ...fallback };
  }

  return {
    enabled: readBool(rawConnector.enabled, fallback.enabled),
    token: readFirstSecret(rawConnector.token, rawConnector.bot_token_enc),
    phoneNumberId: readFirstSecret(rawConnector.phoneNumberId, rawConnector.phone_number_id_enc),
    accessToken: readFirstSecret(rawConnector.accessToken, rawConnector.access_token_enc),
    verifyToken: readFirstSecret(rawConnector.verifyToken, rawConnector.verify_token_enc) || fallback.verifyToken,
    appSecret: readFirstSecret(rawConnector.appSecret, rawConnector.app_secret_enc),
  };
}

function readSystemPromptFile(): string {
  try {
    if (fs.existsSync(SYSTEM_PROMPT_PATH)) {
      const text = fs.readFileSync(SYSTEM_PROMPT_PATH, 'utf8').trim();
      if (text) {
        return text;
      }
    }
  } catch {
    // Fall back to config/default prompt.
  }

  return '';
}

function normalizeConfig(rawConfig: unknown): AppConfig {
  const raw = isPlainObject(rawConfig) ? rawConfig : {};
  const llmRaw = isPlainObject(raw.llm) ? raw.llm : {};
  const securityRaw = isPlainObject(raw.security) ? raw.security : {};
  const skillsRaw = isPlainObject(raw.skills) ? raw.skills : {};
  const connectorsRaw = isPlainObject(raw.connectors) ? raw.connectors : {};

  const provider = readText(llmRaw.provider, DEFAULT_CONFIG.llm.provider);
  const decryptedApiKey = readFirstSecret(llmRaw.apiKey, llmRaw.cloud?.api_key_enc, llmRaw.local_llamacpp?.api_key_enc);
  const inferredGgufPath = readText(llmRaw.ggufPath, DEFAULT_CONFIG.llm.ggufPath) || readText(llmRaw.model);
  const inferredModelName = readText(llmRaw.model) || (inferredGgufPath ? path.basename(inferredGgufPath) : '');
  const baseUrlFromProvider =
    provider === 'llamacpp'
      ? readText(llmRaw.local_llamacpp?.base_url)
      : readText(llmRaw.cloud?.base_url);
  const systemPrompt =
    readSystemPromptFile() ||
    readText(llmRaw.systemPrompt) ||
    readText(llmRaw.system_prompt) ||
    DEFAULT_CONFIG.llm.systemPrompt;
  const fallbackAllowedRoots = readStringArray(skillsRaw.allowed_roots);

  const configuredPort = readNumber(raw.server?.port, DEFAULT_CONFIG.server.port);
  const migratedPort = configuredPort === 8080 ? 8420 : configuredPort;

  return {
    llm: {
      provider,
      apiKey: provider === 'llamacpp' || provider === 'ollama' ? '' : decryptedApiKey,
      model: inferredModelName || DEFAULT_CONFIG.llm.model,
      baseUrl: readText(llmRaw.baseUrl, baseUrlFromProvider || DEFAULT_CONFIG.llm.baseUrl),
      ggufPath: inferredGgufPath,
      systemPrompt,
      requestTimeoutSec: readNumber(llmRaw.requestTimeoutSec ?? llmRaw.request_timeout_sec, DEFAULT_CONFIG.llm.requestTimeoutSec),
      maxTokens: readNumber(llmRaw.maxTokens ?? llmRaw.max_tokens, DEFAULT_CONFIG.llm.maxTokens),
      temperature: readNumber(llmRaw.temperature, DEFAULT_CONFIG.llm.temperature),
    },
    server: {
      port: migratedPort,
      host: readText(raw.server?.host, DEFAULT_CONFIG.server.host),
    },
    connectors: {
      telegram: normalizeConnectorConfig(connectorsRaw.telegram, DEFAULT_CONFIG.connectors.telegram),
      discord: normalizeConnectorConfig(connectorsRaw.discord, DEFAULT_CONFIG.connectors.discord),
      whatsapp: normalizeConnectorConfig(connectorsRaw.whatsapp, DEFAULT_CONFIG.connectors.whatsapp),
    },
    skills: {
      filesystem: normalizeSkillConfig(skillsRaw.filesystem, DEFAULT_CONFIG.skills.filesystem),
      web: normalizeSkillConfig(skillsRaw.web, DEFAULT_CONFIG.skills.web),
      shell: normalizeSkillConfig(skillsRaw.shell, DEFAULT_CONFIG.skills.shell),
    },
    security: {
      encryptSecrets: readBool(securityRaw.encryptSecrets, DEFAULT_CONFIG.security.encryptSecrets),
      consentRequired: readBool(securityRaw.consentRequired, DEFAULT_CONFIG.security.consentRequired),
      allowedWorkDir: path.resolve(
        readText(securityRaw.allowedWorkDir, fallbackAllowedRoots[0] || DEFAULT_CONFIG.security.allowedWorkDir),
      ),
    },
  };
}

function buildPersistedConfig(rawBase: Record<string, any>, config: AppConfig): Record<string, any> {
  const next = structuredClone(rawBase);
  const isLocalProvider = config.llm.provider === 'llamacpp' || config.llm.provider === 'ollama';
  const storedApiKey = config.llm.provider === 'llamacpp' || config.llm.provider === 'ollama' ? '' : config.llm.apiKey;
  const existingCloudBaseUrl = readText(next.llm?.cloud?.base_url);
  next.llm ??= {};
  next.llm.provider = config.llm.provider;
  next.llm.model = config.llm.model;
  next.llm.baseUrl = config.llm.baseUrl;
  next.llm.ggufPath = config.llm.ggufPath;
  next.llm.systemPrompt = config.llm.systemPrompt;
  next.llm.system_prompt = config.llm.systemPrompt;
  next.llm.requestTimeoutSec = config.llm.requestTimeoutSec;
  next.llm.request_timeout_sec = config.llm.requestTimeoutSec;
  next.llm.maxTokens = config.llm.maxTokens;
  next.llm.max_tokens = config.llm.maxTokens;
  next.llm.temperature = config.llm.temperature;
  next.llm.apiKey = encrypt(storedApiKey);
  next.llm.cloud ??= {};
  next.llm.cloud.base_url = isLocalProvider
    ? (
      existingCloudBaseUrl &&
        !existingCloudBaseUrl.startsWith('http://127.0.0.1:8081')
        ? existingCloudBaseUrl
        : 'https://api.openai.com/v1'
    )
    : (config.llm.baseUrl || 'https://api.openai.com/v1');
  next.llm.cloud.api_key_enc = encrypt(storedApiKey);
  next.llm.local_llamacpp ??= {};
  next.llm.local_llamacpp.base_url = isLocalProvider
    ? (config.llm.baseUrl || 'http://127.0.0.1:8081')
    : readText(next.llm.local_llamacpp.base_url, 'http://127.0.0.1:8081') || 'http://127.0.0.1:8081';
  next.llm.local_llamacpp.api_key_enc = '';

  next.server ??= {};
  next.server.port = config.server.port;
  next.server.host = config.server.host;

  next.connectors ??= {};
  next.connectors.telegram ??= {};
  next.connectors.telegram.enabled = config.connectors.telegram.enabled;
  next.connectors.telegram.token = encrypt(config.connectors.telegram.token);
  next.connectors.telegram.bot_token_enc = encrypt(config.connectors.telegram.token);

  next.connectors.discord ??= {};
  next.connectors.discord.enabled = config.connectors.discord.enabled;
  next.connectors.discord.token = encrypt(config.connectors.discord.token);
  next.connectors.discord.bot_token_enc = encrypt(config.connectors.discord.token);

  next.connectors.whatsapp ??= {};
  next.connectors.whatsapp.enabled = config.connectors.whatsapp.enabled;
  next.connectors.whatsapp.phoneNumberId = config.connectors.whatsapp.phoneNumberId;
  next.connectors.whatsapp.phone_number_id_enc = encrypt(config.connectors.whatsapp.phoneNumberId);
  next.connectors.whatsapp.accessToken = encrypt(config.connectors.whatsapp.accessToken);
  next.connectors.whatsapp.access_token_enc = encrypt(config.connectors.whatsapp.accessToken);
  next.connectors.whatsapp.verifyToken = encrypt(config.connectors.whatsapp.verifyToken);
  next.connectors.whatsapp.verify_token_enc = encrypt(config.connectors.whatsapp.verifyToken);
  next.connectors.whatsapp.appSecret = encrypt(config.connectors.whatsapp.appSecret);
  next.connectors.whatsapp.app_secret_enc = encrypt(config.connectors.whatsapp.appSecret);

  next.skills ??= {};
  next.skills.filesystem = {
    enabled: config.skills.filesystem.enabled,
    requiresConsent: config.skills.filesystem.requiresConsent,
    allowedPaths: config.skills.filesystem.allowedPaths ?? [],
  };
  next.skills.web = {
    enabled: config.skills.web.enabled,
    requiresConsent: config.skills.web.requiresConsent,
  };
  next.skills.shell = {
    enabled: config.skills.shell.enabled,
    requiresConsent: config.skills.shell.requiresConsent,
  };
  delete next.skills.enabled;
  delete next.skills.allowed_roots;

  next.security ??= {};
  next.security.encryptSecrets = config.security.encryptSecrets;
  next.security.consentRequired = config.security.consentRequired;
  next.security.allowedWorkDir = config.security.allowedWorkDir;

  return next;
}

export function ensureSystemPrompt(): void {
  ensureDataDirs();
  if (!fs.existsSync(SYSTEM_PROMPT_PATH)) {
    fs.writeFileSync(SYSTEM_PROMPT_PATH, DEFAULT_SYSTEM_PROMPT, 'utf8');
  }
}

export function getSystemPrompt(): string {
  ensureSystemPrompt();
  const fromFile = readSystemPromptFile();
  if (fromFile) {
    return fromFile;
  }

  return loadConfig().llm.systemPrompt || DEFAULT_SYSTEM_PROMPT;
}

export function saveSystemPrompt(prompt: string): void {
  ensureSystemPrompt();
  fs.writeFileSync(SYSTEM_PROMPT_PATH, prompt.trim() || DEFAULT_SYSTEM_PROMPT, 'utf8');

  if (_config) {
    _config.llm.systemPrompt = prompt.trim() || DEFAULT_SYSTEM_PROMPT;
  }
}

export function loadConfig(): AppConfig {
  if (_config) {
    return _config;
  }

  ensureDataDirs();
  ensureSystemPrompt();

  if (fs.existsSync(CONFIG_PATH)) {
    const raw = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
    _rawConfig = isPlainObject(raw) ? raw : {};
  } else {
    _rawConfig = {};
  }

  _config = normalizeConfig(_rawConfig);
  return _config;
}

export function saveConfig(updates: Partial<AppConfig>): AppConfig {
  const current = loadConfig();
  const merged = deepMerge(structuredClone(current), updates);

  if (updates.llm?.systemPrompt !== undefined) {
    saveSystemPrompt(updates.llm.systemPrompt);
    merged.llm.systemPrompt = getSystemPrompt();
  }

  const normalized = normalizeConfig(buildPersistedConfig(_rawConfig ?? {}, merged));
  const toSave = buildPersistedConfig(_rawConfig ?? {}, normalized);

  fs.writeFileSync(CONFIG_PATH, JSON.stringify(toSave, null, 2), 'utf8');
  _rawConfig = toSave;
  _config = normalized;
  return _config;
}

export function resetConfigCache(): void {
  _config = null;
  _rawConfig = null;
}
