import * as fs from 'fs/promises';
import * as path from 'path';
import { MODELS_DIR } from '../paths.js';

export interface LocalModelInfo {
  name: string;
  path: string;
  sizeBytes: number;
}

async function walkModels(rootDir: string, limit: number, results: LocalModelInfo[]): Promise<void> {
  const stack = [rootDir];

  while (stack.length > 0 && results.length < limit) {
    const current = stack.pop() as string;
    let entries;

    try {
      entries = await fs.readdir(current, { withFileTypes: true });
    } catch {
      continue;
    }

    for (const entry of entries) {
      if (results.length >= limit) break;

      const fullPath = path.join(current, entry.name);
      if (entry.isDirectory()) {
        stack.push(fullPath);
        continue;
      }

      if (!entry.isFile() || !entry.name.toLowerCase().endsWith('.gguf')) {
        continue;
      }

      try {
        const stat = await fs.stat(fullPath);
        results.push({ name: entry.name, path: fullPath, sizeBytes: stat.size });
      } catch {
        // Ignore unreadable files and continue discovery.
      }
    }
  }
}

export async function discoverLocalModels(limit = 50): Promise<LocalModelInfo[]> {
  const results: LocalModelInfo[] = [];
  await walkModels(MODELS_DIR, limit, results);
  return results.sort((a, b) => a.name.localeCompare(b.name));
}
