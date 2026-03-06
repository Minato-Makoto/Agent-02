import * as path from 'path';
import { fileURLToPath } from 'url';

const moduleDir = path.dirname(fileURLToPath(import.meta.url));

export const PROJECT_ROOT = path.resolve(moduleDir, '..');
export const DATA_DIR = path.join(PROJECT_ROOT, 'data');
export const CONFIG_PATH = path.join(DATA_DIR, 'config.json');
export const SECRET_KEY_PATH = path.join(DATA_DIR, '.secret_key');
export const WORKSPACE_DIR = path.join(DATA_DIR, 'workspace');
export const SYSTEM_PROMPT_PATH = path.join(DATA_DIR, 'instructions', 'system.md');
export const UI_DIST_DIR = path.join(PROJECT_ROOT, 'ui', 'dist');
export const LLAMA_CPP_DIR = path.resolve(PROJECT_ROOT, '..', 'llama.cpp');
export const MODELS_DIR = path.resolve(PROJECT_ROOT, '..', 'models');

export const LLAMA_SERVER_CANDIDATES = [
  path.join(LLAMA_CPP_DIR, 'llama-server.exe'),
  path.join(LLAMA_CPP_DIR, 'llama-server'),
  'C:\\llama.cpp\\llama-server.exe',
  'llama-server',
];
