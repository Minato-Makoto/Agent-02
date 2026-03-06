// ═══════════════════════════════════════════════════
// Agent-02 — Sandboxed Skill Registry
// ═══════════════════════════════════════════════════

import type { ToolDefinition } from '../llm/provider.js';
import { log } from '../gateway/eventbus.js';
import { loadConfig } from '../config.js';

export interface Skill {
    name: string;
    description: string;
    parameters: Record<string, any>;
    requiresConsent: boolean;
    execute: (args: Record<string, any>) => Promise<string>;
}

class SkillRegistryImpl {
    private skills = new Map<string, Skill>();

    register(skill: Skill): void {
        const cfg = loadConfig();
        const skillCfg = skill.name in cfg.skills
            ? cfg.skills[skill.name as keyof typeof cfg.skills]
            : undefined;
        if (skillCfg && !skillCfg.enabled) {
            log('info', 'skills', `Skill "${skill.name}" is disabled in config`);
            return;
        }
        const normalizedSkill: Skill = {
            ...skill,
            requiresConsent: skillCfg ? skillCfg.requiresConsent : skill.requiresConsent,
        };
        this.skills.set(skill.name, normalizedSkill);
        log('info', 'skills', `Registered skill: ${skill.name} (consent: ${normalizedSkill.requiresConsent})`);
    }

    getSkill(name: string): Skill | undefined {
        return this.skills.get(name);
    }

    getToolDefinitions(): ToolDefinition[] {
        return Array.from(this.skills.values()).map(s => ({
            type: 'function' as const,
            function: { name: s.name, description: s.description, parameters: s.parameters },
        }));
    }

    async execute(name: string, args: Record<string, any>): Promise<string> {
        const skill = this.skills.get(name);
        if (!skill) return `Error: Unknown skill "${name}"`;
        try {
            return await skill.execute(args);
        } catch (err: any) {
            log('error', 'skills', `Skill "${name}" failed: ${err.message}`);
            return `Error executing "${name}": ${err.message}`;
        }
    }
}

export const skillRegistry = new SkillRegistryImpl();
