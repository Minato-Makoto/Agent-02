import * as fs from 'fs/promises';
import * as path from 'path';
import { loadConfig } from '../config.js';
import { resolveInside } from '../utils/path.js';
import { skillRegistry, type Skill } from './registry.js';

function sanitizePath(filePath: string): string {
  return resolveInside(loadConfig().security.allowedWorkDir, filePath);
}

const readFile: Skill = {
  name: 'read_file',
  description: 'Read a file from the allowed workspace directory',
  requiresConsent: false,
  parameters: {
    type: 'object',
    properties: {
      path: { type: 'string', description: 'Relative path within workspace' },
    },
    required: ['path'],
  },
  async execute(args) {
    const safePath = sanitizePath(args.path);
    const content = await fs.readFile(safePath, 'utf8');
    return content.length > 10000 ? `${content.slice(0, 10000)}\n...(truncated)` : content;
  },
};

const writeFile: Skill = {
  name: 'write_file',
  description: 'Write content to a file in the allowed workspace directory',
  requiresConsent: false,
  parameters: {
    type: 'object',
    properties: {
      path: { type: 'string', description: 'Relative path within workspace' },
      content: { type: 'string', description: 'File content to write' },
    },
    required: ['path', 'content'],
  },
  async execute(args) {
    const safePath = sanitizePath(args.path);
    await fs.mkdir(path.dirname(safePath), { recursive: true });
    await fs.writeFile(safePath, args.content, 'utf8');
    return `File written: ${args.path}`;
  },
};

const listDir: Skill = {
  name: 'list_directory',
  description: 'List files in a directory within the allowed workspace',
  requiresConsent: false,
  parameters: {
    type: 'object',
    properties: {
      path: { type: 'string', description: 'Relative directory path within workspace (default: root)' },
    },
  },
  async execute(args) {
    const safePath = sanitizePath(args.path || '.');
    const entries = await fs.readdir(safePath, { withFileTypes: true });
    return entries.map((entry) => `${entry.isDirectory() ? '[DIR]' : '[FILE]'} ${entry.name}`).join('\n') || '(empty directory)';
  },
};

export function registerFilesystemSkills(): void {
  fs.mkdir(loadConfig().security.allowedWorkDir, { recursive: true }).catch(() => {});

  skillRegistry.register(readFile);
  skillRegistry.register(writeFile);
  skillRegistry.register(listDir);
}
