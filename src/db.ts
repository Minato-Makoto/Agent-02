// ═══════════════════════════════════════════════════
// Agent-02 — SQLite Database (sql.js, pure WASM)
// ═══════════════════════════════════════════════════

import initSqlJs, { type Database as SqlJsDb } from 'sql.js';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DATA_DIR = path.join(__dirname, '..', 'data');
const DB_PATH = path.join(DATA_DIR, 'agent02.db');

let _db: SqlJsDb | null = null;

export async function initDb(): Promise<void> {
  if (_db) return;
  if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });

  const SQL = await initSqlJs();
  if (fs.existsSync(DB_PATH)) {
    _db = new SQL.Database(fs.readFileSync(DB_PATH));
  } else {
    _db = new SQL.Database();
  }
  initSchema();
  persist();
}

function db(): SqlJsDb {
  if (!_db) throw new Error('DB not initialized. Call initDb() first.');
  return _db;
}

function persist(): void {
  if (!_db) return;
  const data = _db.export();
  fs.writeFileSync(DB_PATH, Buffer.from(data));
}

// Auto-persist every 10 seconds
setInterval(() => { try { persist(); } catch { } }, 10000);

function initSchema(): void {
  db().run(`
    CREATE TABLE IF NOT EXISTS sessions (
      id TEXT PRIMARY KEY, platform TEXT NOT NULL, platform_uid TEXT NOT NULL,
      display_name TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT DEFAULT (datetime('now')), UNIQUE(platform, platform_uid)
    )
  `);
  db().run(`
    CREATE TABLE IF NOT EXISTS messages (
      id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
      role TEXT NOT NULL, content TEXT NOT NULL DEFAULT '',
      tool_calls TEXT DEFAULT NULL, tool_call_id TEXT DEFAULT NULL,
      created_at TEXT DEFAULT (datetime('now'))
    )
  `);
  db().run(`
    CREATE TABLE IF NOT EXISTS logs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      level TEXT NOT NULL DEFAULT 'info', source TEXT NOT NULL DEFAULT 'system',
      message TEXT NOT NULL, data TEXT DEFAULT NULL,
      created_at TEXT DEFAULT (datetime('now'))
    )
  `);
  db().run(`
    CREATE TABLE IF NOT EXISTS consent_queue (
      id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
      skill_name TEXT NOT NULL, args TEXT NOT NULL,
      status TEXT DEFAULT 'pending',
      created_at TEXT DEFAULT (datetime('now')), resolved_at TEXT DEFAULT NULL
    )
  `);
}

// ── Helpers ──

function queryAll(sql: string, params: any[] = []): any[] {
  const stmt = db().prepare(sql);
  if (params.length) stmt.bind(params);
  const results: any[] = [];
  while (stmt.step()) results.push(stmt.getAsObject());
  stmt.free();
  return results;
}

function queryOne(sql: string, params: any[] = []): any | null {
  const rows = queryAll(sql, params);
  return rows.length > 0 ? rows[0] : null;
}

function run(sql: string, params: any[] = []): void {
  db().run(sql, params);
  persist();
}

export function getDb() { return db(); }

export function getOrCreateSession(platform: string, uid: string, name = ''): string {
  // 1. Check if uid is an exact session ID (used by Web UI to resume sessions)
  const rowById = queryOne('SELECT id FROM sessions WHERE id = ?', [uid]);
  if (rowById) {
    run("UPDATE sessions SET updated_at = datetime('now') WHERE id = ?", [rowById.id]);
    return rowById.id as string;
  }

  // 2. Fallback to platform + uid unique pair for bot platforms (Telegram, Discord)
  const row = queryOne('SELECT id FROM sessions WHERE platform = ? AND platform_uid = ?', [platform, uid]);
  if (row) {
    run("UPDATE sessions SET updated_at = datetime('now') WHERE id = ?", [row.id]);
    return row.id as string;
  }

  const id = platform === 'webui' && uid.trim()
    ? uid.trim()
    : `${platform}_${uid}_${Date.now()}`;
  run('INSERT INTO sessions (id, platform, platform_uid, display_name) VALUES (?, ?, ?, ?)', [id, platform, uid, name]);
  return id;
}

export function saveMessage(sessionId: string, role: string, content: string, toolCalls?: any, toolCallId?: string): void {
  run('INSERT INTO messages (session_id, role, content, tool_calls, tool_call_id) VALUES (?, ?, ?, ?, ?)',
    [sessionId, role, content, toolCalls ? JSON.stringify(toolCalls) : null, toolCallId ?? null]);
}

export function getHistory(sessionId: string, limit = 50): any[] {
  return queryAll('SELECT role, content, tool_calls, tool_call_id FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?', [sessionId, limit]).reverse();
}

export function addLog(level: string, source: string, message: string, data?: any): void {
  try { run('INSERT INTO logs (level, source, message, data) VALUES (?, ?, ?, ?)', [level, source, message, data ? JSON.stringify(data) : null]); } catch { }
}

export function getRecentLogs(limit = 100): any[] {
  return queryAll('SELECT * FROM logs ORDER BY id DESC LIMIT ?', [limit]).reverse();
}

export function getAllSessions(): any[] {
  return queryAll(`SELECT s.id, s.platform, s.platform_uid, s.display_name, s.created_at, s.updated_at, COUNT(m.id) as message_count
    FROM sessions s LEFT JOIN messages m ON s.id = m.session_id GROUP BY s.id ORDER BY s.updated_at DESC`);
}

export function addConsentRequest(id: string, sessionId: string, skill: string, args: any): void {
  run('INSERT INTO consent_queue (id, session_id, skill_name, args) VALUES (?, ?, ?, ?)', [id, sessionId, skill, JSON.stringify(args)]);
}

export function resolveConsent(id: string, approved: boolean): void {
  run("UPDATE consent_queue SET status = ?, resolved_at = datetime('now') WHERE id = ?", [approved ? 'approved' : 'denied', id]);
}

export function getPendingConsents(): any[] {
  return queryAll("SELECT * FROM consent_queue WHERE status = 'pending' ORDER BY created_at");
}
