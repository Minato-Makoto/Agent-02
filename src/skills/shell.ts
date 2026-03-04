// ═══════════════════════════════════════════════════
// Agent-02 — Shell Skill (REQUIRES CONSENT)
// Human-in-the-Loop: every command must be approved via UI
// ═══════════════════════════════════════════════════

import { execSync } from 'child_process';
import { skillRegistry, type Skill } from './registry.js';

const shellExec: Skill = {
    name: 'shell_exec',
    description: 'Execute a shell command on the host machine. REQUIRES explicit user approval before execution.',
    requiresConsent: true, // Always requires admin approval
    parameters: {
        type: 'object',
        properties: {
            command: { type: 'string', description: 'Shell command to execute' },
        },
        required: ['command'],
    },
    async execute(args) {
        // This code only runs AFTER consent is granted
        try {
            const output = execSync(args.command, {
                timeout: 30000,
                maxBuffer: 1024 * 1024, // 1MB
                encoding: 'utf8',
                shell: process.platform === 'win32' ? 'powershell.exe' : '/bin/bash',
            });
            const trimmed = output.trim();
            return trimmed.length > 5000 ? trimmed.slice(0, 5000) + '\n...(truncated)' : trimmed || '(no output)';
        } catch (err: any) {
            return `Command failed (exit ${err.status}): ${err.stderr || err.message}`;
        }
    },
};

export function registerShellSkill(): void {
    skillRegistry.register(shellExec);
}
