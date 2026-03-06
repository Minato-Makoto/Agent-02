import { execFileSync } from 'child_process';
import { loadConfig } from '../config.js';
import { skillRegistry, type Skill } from './registry.js';

const BLOCKED_PATTERNS = [
  /\brm\b/i,
  /\bdel\b/i,
  /\bformat\b/i,
  /\bshutdown\b/i,
  /\breboot\b/i,
  /\bmkfs\b/i,
  /\bdiskpart\b/i,
  /\breg\s+delete\b/i,
  /\bcipher\s*\/w\b/i,
  /\bdd\b/i,
  /\bbcdedit\b/i,
];

function assertSafeCommand(command: string): void {
  const normalized = command.trim();
  if (!normalized) {
    throw new Error('Command cannot be empty.');
  }

  for (const pattern of BLOCKED_PATTERNS) {
    if (pattern.test(normalized)) {
      throw new Error('Blocked command: destructive system operations are disabled in Agent-02.');
    }
  }
}

function executeCommand(command: string): string {
  const cwd = loadConfig().security.allowedWorkDir;

  if (process.platform === 'win32') {
    return execFileSync('powershell.exe', ['-NoProfile', '-Command', command], {
      cwd,
      timeout: 30000,
      maxBuffer: 1024 * 1024,
      encoding: 'utf8',
    });
  }

  return execFileSync('/bin/bash', ['-lc', command], {
    cwd,
    timeout: 30000,
    maxBuffer: 1024 * 1024,
    encoding: 'utf8',
  });
}

const shellExec: Skill = {
  name: 'shell_exec',
  description: 'Execute a shell command inside the workspace. Requires explicit user approval before execution.',
  requiresConsent: true,
  parameters: {
    type: 'object',
    properties: {
      command: { type: 'string', description: 'Shell command to execute' },
    },
    required: ['command'],
  },
  async execute(args) {
    try {
      assertSafeCommand(args.command);
      const output = executeCommand(args.command).trim();
      return output.length > 5000 ? `${output.slice(0, 5000)}\n...(truncated)` : output || '(no output)';
    } catch (err: any) {
      return `Command failed: ${err.stderr || err.message}`;
    }
  },
};

export function registerShellSkill(): void {
  skillRegistry.register(shellExec);
}
