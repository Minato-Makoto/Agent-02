import { spawn, spawnSync } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { setTimeout as delay } from "node:timers/promises";
import JSON5 from "json5";

const ROOT_DIR = process.cwd();
const LLAMA_PORT = 8000;

function normalizeString(value) {
  if (typeof value !== "string") {
    return "";
  }
  return value.trim();
}

function stripWrappingQuotes(value) {
  const trimmed = normalizeString(value);
  if (trimmed.length >= 2 && trimmed.startsWith('"') && trimmed.endsWith('"')) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

function resolveFromRoot(input, fallback) {
  const raw = stripWrappingQuotes(input) || stripWrappingQuotes(fallback);
  if (!raw) {
    return "";
  }
  return path.isAbsolute(raw) ? path.normalize(raw) : path.resolve(ROOT_DIR, raw);
}

function parseInteger(value, fallback) {
  const trimmed = normalizeString(value);
  if (!trimmed) {
    return fallback;
  }
  const parsed = Number.parseInt(trimmed, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function parseArgString(input) {
  const source = normalizeString(input);
  if (!source) {
    return [];
  }

  const args = [];
  let current = "";
  let inQuotes = false;

  for (const char of source) {
    if (char === '"') {
      inQuotes = !inQuotes;
      continue;
    }
    if (!inQuotes && /\s/.test(char)) {
      if (current) {
        args.push(current);
        current = "";
      }
      continue;
    }
    current += char;
  }

  if (current) {
    args.push(current);
  }
  return args;
}

function runPowerShell(script, options = {}) {
  const result = spawnSync(
    "powershell.exe",
    ["-NoProfile", "-NonInteractive", "-Command", script],
    {
      encoding: "utf8",
      windowsHide: true,
    },
  );

  if (result.error) {
    if (options.allowFailure) {
      return "";
    }
    throw result.error;
  }

  if (result.status !== 0) {
    if (options.allowFailure) {
      return "";
    }
    const stderr = normalizeString(result.stderr);
    const stdout = normalizeString(result.stdout);
    throw new Error(stderr || stdout || `PowerShell exited with code ${result.status}`);
  }

  return normalizeString(result.stdout);
}

function parseJsonArray(output) {
  if (!output) {
    return [];
  }
  const parsed = JSON.parse(output);
  return Array.isArray(parsed) ? parsed : [parsed];
}

function getListeningPidsFromNetstat(port) {
  const result = spawnSync("netstat", ["-ano", "-p", "TCP"], {
    encoding: "utf8",
    windowsHide: true,
  });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    const stderr = normalizeString(result.stderr);
    throw new Error(stderr || `netstat exited with code ${result.status}`);
  }

  const pids = new Set();
  for (const rawLine of result.stdout.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line.includes("LISTENING")) {
      continue;
    }
    const parts = line.split(/\s+/);
    if (parts.length < 5) {
      continue;
    }
    const localAddress = parts[1];
    const state = parts[3];
    const pid = Number.parseInt(parts[4], 10);
    if (state !== "LISTENING" || !Number.isFinite(pid)) {
      continue;
    }
    if (localAddress.endsWith(`:${port}`) || localAddress.endsWith(`]:${port}`)) {
      pids.add(pid);
    }
  }

  return [...pids];
}

function getListeningPids(port) {
  try {
    const output = runPowerShell(
      `
$items = @(Get-NetTCPConnection -State Listen -LocalPort ${port} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
if ($items.Count -gt 0) {
  $items | ConvertTo-Json -Compress
}
      `,
      { allowFailure: true },
    );
    if (!output) {
      return [];
    }
    return parseJsonArray(output)
      .map((value) => Number.parseInt(String(value), 10))
      .filter((value) => Number.isFinite(value));
  } catch {
    return getListeningPidsFromNetstat(port);
  }
}

function getProcessInfo(pid) {
  const safePid = Number.parseInt(String(pid), 10);
  if (!Number.isFinite(safePid)) {
    return null;
  }
  const output = runPowerShell(
    `
$proc = Get-CimInstance Win32_Process -Filter "ProcessId=${safePid}" -ErrorAction SilentlyContinue | Select-Object ProcessId,Name,CommandLine
if ($null -ne $proc) {
  $proc | ConvertTo-Json -Compress
}
    `,
    { allowFailure: true },
  );
  if (!output) {
    return null;
  }
  return JSON.parse(output);
}

async function ensureDir(dir) {
  await fsp.mkdir(dir, { recursive: true });
}

function appendLog(logPath, line) {
  fs.appendFileSync(logPath, `${line}\n`, "utf8");
}

function ensurePnpmShim() {
  if (process.platform !== "win32") {
    return;
  }
  const tempRoot =
    normalizeString(process.env.TEMP) || normalizeString(process.env.TMP) || ROOT_DIR;
  const shimDir = path.join(tempRoot, "agent02-pnpm-shim");
  fs.mkdirSync(shimDir, { recursive: true });
  fs.writeFileSync(
    path.join(shimDir, "pnpm.cmd"),
    "@echo off\r\ncall corepack pnpm %*\r\nexit /b %errorlevel%\r\n",
    "utf8",
  );
  process.env.PATH = `${shimDir}${path.delimiter}${process.env.PATH ?? ""}`;
}

function spawnDetached(command, args, logPath, cwd) {
  appendLog(
    logPath,
    `[${new Date().toISOString()}] Starting: ${command} ${args.map((arg) => JSON.stringify(arg)).join(" ")}`,
  );
  const logFd = fs.openSync(logPath, "a");
  try {
    const child = spawn(command, args, {
      cwd,
      detached: true,
      env: process.env,
      stdio: ["ignore", logFd, logFd],
      windowsHide: true,
    });
    if (!child.pid) {
      throw new Error(`Failed to spawn ${command}`);
    }
    child.unref();
  } finally {
    fs.closeSync(logFd);
  }
}

async function fetchJson(url, timeoutMs) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return await response.json();
  } finally {
    clearTimeout(timeout);
  }
}

async function fetchGatewayStatus(url, timeoutMs) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { redirect: "manual", signal: controller.signal });
    return response.status;
  } finally {
    clearTimeout(timeout);
  }
}

function isModelList(payload) {
  return Boolean(payload) && typeof payload === "object" && Array.isArray(payload.data);
}

function extractModelIds(payload) {
  if (!isModelList(payload)) {
    return [];
  }
  return [...new Set(payload.data.map((entry) => normalizeString(entry?.id)).filter(Boolean))];
}

async function waitForModels(timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  const url = `http://127.0.0.1:${LLAMA_PORT}/v1/models`;
  let lastError = "No response yet.";

  while (Date.now() < deadline) {
    try {
      const payload = await fetchJson(url, 2500);
      if (!isModelList(payload)) {
        throw new Error("Endpoint did not return an OpenAI-compatible models payload.");
      }
      const ids = extractModelIds(payload);
      if (ids.length === 0) {
        throw new Error("Endpoint returned zero models.");
      }
      return ids;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
      await delay(1000);
    }
  }

  throw new Error(`Timed out waiting for ${url}. Last error: ${lastError}`);
}

async function waitForGateway(timeoutMs, port) {
  const deadline = Date.now() + timeoutMs;
  const url = `http://127.0.0.1:${port}/`;
  let lastError = "No response yet.";

  while (Date.now() < deadline) {
    try {
      await fetchGatewayStatus(url, 2500);
      return;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
      await delay(1000);
    }
  }

  throw new Error(`Timed out waiting for ${url}. Last error: ${lastError}`);
}

function generateToken() {
  return crypto.randomBytes(24).toString("base64url");
}

function readPrimaryModel(config) {
  const model = config?.agents?.defaults?.model;
  if (typeof model === "string") {
    return normalizeString(model);
  }
  if (model && typeof model === "object" && typeof model.primary === "string") {
    return normalizeString(model.primary);
  }
  return "";
}

function setPrimaryModel(config, primary) {
  config.agents ??= {};
  config.agents.defaults ??= {};
  const currentModel = config.agents.defaults.model;
  if (currentModel && typeof currentModel === "object" && !Array.isArray(currentModel)) {
    currentModel.primary = primary;
    return;
  }
  config.agents.defaults.model = { primary };
}

async function loadConfig(configPath) {
  if (!fs.existsSync(configPath)) {
    return { config: {}, changed: false };
  }

  const raw = await fsp.readFile(configPath, "utf8");
  if (!normalizeString(raw)) {
    return { config: {}, changed: false };
  }

  let parsed;
  try {
    parsed = JSON5.parse(raw);
  } catch (error) {
    throw new Error(
      `Config parse failed for ${configPath}: ${error instanceof Error ? error.message : String(error)}`,
    );
  }

  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`Config at ${configPath} must be a JSON object.`);
  }

  return { config: parsed, changed: false };
}

async function writeConfig(configPath, config) {
  await ensureDir(path.dirname(configPath));
  await fsp.writeFile(configPath, `${JSON.stringify(config, null, 2)}\n`, "utf8");
}

async function bootstrapConfig(configPath, workspaceDir, liveModelIds, defaultModelOverride) {
  const { config } = await loadConfig(configPath);
  let changed = false;

  const liveModelIdsSorted = [...liveModelIds].sort((left, right) => left.localeCompare(right));
  const defaultModelId = defaultModelOverride
    ? liveModelIdsSorted.find((id) => id === defaultModelOverride)
    : liveModelIdsSorted[0];

  if (defaultModelOverride && !defaultModelId) {
    throw new Error(`DEFAULT_MODEL_ID "${defaultModelOverride}" was not found in /v1/models.`);
  }
  if (!defaultModelId) {
    throw new Error("No models were available from llama-server.");
  }

  config.gateway ??= {};
  config.gateway.auth ??= {};
  config.agents ??= {};
  config.agents.defaults ??= {};

  if (config.gateway.mode !== "local") {
    config.gateway.mode = "local";
    changed = true;
  }

  if (config.gateway.bind !== "loopback") {
    config.gateway.bind = "loopback";
    changed = true;
  }

  if (config.gateway.auth.mode !== "token") {
    config.gateway.auth.mode = "token";
    changed = true;
  }

  if (!normalizeString(config.gateway.auth.token)) {
    config.gateway.auth.token = generateToken();
    changed = true;
  }

  if (!normalizeString(config.agents.defaults.workspace)) {
    config.agents.defaults.workspace = workspaceDir;
    changed = true;
  }

  const currentPrimary = readPrimaryModel(config);
  const liveRefs = new Set(liveModelIdsSorted.map((id) => `vllm/${id}`));
  const nextPrimary = `vllm/${defaultModelId}`;
  if (defaultModelOverride && currentPrimary !== nextPrimary) {
    setPrimaryModel(config, nextPrimary);
    changed = true;
  } else if (!currentPrimary || !liveRefs.has(currentPrimary)) {
    setPrimaryModel(config, nextPrimary);
    changed = true;
  }

  if (changed) {
    await writeConfig(configPath, config);
  }

  return { config, defaultModelId };
}

function ensureFileExists(filePath, label) {
  if (!fs.existsSync(filePath)) {
    throw new Error(`${label} was not found at ${filePath}`);
  }
}

function ensureDirectoryExists(dirPath, label) {
  if (!fs.existsSync(dirPath)) {
    throw new Error(`${label} was not found at ${dirPath}`);
  }
}

async function ensureLlamaRunning(llamaExe, modelsDir, llamaLogPath, extraArgs, gpuLayers) {
  const listeningPids = getListeningPids(LLAMA_PORT);
  if (listeningPids.length > 0) {
    const info = getProcessInfo(listeningPids[0]);
    const name = normalizeString(info?.Name).toLowerCase();
    if (name !== "llama-server.exe") {
      throw new Error(
        `Port ${LLAMA_PORT} is already in use by ${info?.Name ?? `PID ${listeningPids[0]}`}.`,
      );
    }
    return await waitForModels(60000);
  }

  const args = ["--models-dir", modelsDir, "--host", "127.0.0.1", "--port", String(LLAMA_PORT)];
  if (normalizeString(gpuLayers)) {
    args.push("--gpu-layers", normalizeString(gpuLayers));
  }
  args.push(...extraArgs);

  spawnDetached(llamaExe, args, llamaLogPath, path.dirname(llamaExe));
  try {
    return await waitForModels(60000);
  } catch (error) {
    throw new Error(
      `llama-server failed to become ready. Check ${llamaLogPath}. ${error instanceof Error ? error.message : String(error)}`,
    );
  }
}

async function ensureGatewayRunning(rootDir, gatewayPort, gatewayLogPath) {
  const listeningPids = getListeningPids(gatewayPort);
  if (listeningPids.length > 0) {
    const info = getProcessInfo(listeningPids[0]);
    const commandLine = normalizeString(info?.CommandLine);
    if (!/openclaw\.mjs/i.test(commandLine) || !/\bgateway\b/i.test(commandLine)) {
      throw new Error(
        `Port ${gatewayPort} is already in use by ${info?.Name ?? `PID ${listeningPids[0]}`}.`,
      );
    }
    await waitForGateway(60000, gatewayPort);
    return;
  }

  spawnDetached(
    process.execPath,
    [path.join(rootDir, "openclaw.mjs"), "gateway", "run", "--port", String(gatewayPort)],
    gatewayLogPath,
    rootDir,
  );

  try {
    await waitForGateway(60000, gatewayPort);
  } catch (error) {
    throw new Error(
      `OpenClaw gateway failed to become ready. Check ${gatewayLogPath}. ${error instanceof Error ? error.message : String(error)}`,
    );
  }
}

async function main() {
  const gatewayPort = parseInteger(
    process.env.GATEWAY_PORT ?? process.env.OPENCLAW_GATEWAY_PORT,
    18789,
  );
  if (!Number.isFinite(gatewayPort) || gatewayPort <= 0) {
    throw new Error(`Invalid GATEWAY_PORT: ${process.env.GATEWAY_PORT ?? ""}`);
  }

  const stateDir = resolveFromRoot(process.env.OPENCLAW_STATE_DIR, ".openclaw");
  const configPath = resolveFromRoot(
    process.env.OPENCLAW_CONFIG_PATH,
    path.join(stateDir, "openclaw.json"),
  );
  const workspaceDir = path.join(stateDir, "workspace");
  const logsDir = path.join(stateDir, "logs");
  const llamaLogPath = path.join(logsDir, "llama-server.log");
  const gatewayLogPath = path.join(logsDir, "gateway.log");
  const llamaExe = resolveFromRoot(process.env.LLAMA_SERVER_EXE, "..\\llama.cpp\\llama-server.exe");
  const modelsDir = resolveFromRoot(process.env.MODELS_DIR, "..\\models");
  const defaultModelOverride = normalizeString(process.env.DEFAULT_MODEL_ID);
  const extraArgs = parseArgString(process.env.EXTRA_LLAMA_ARGS);
  const gpuLayers = process.env.GPU_LAYERS;

  ensureFileExists(llamaExe, "llama-server.exe");
  ensureDirectoryExists(modelsDir, "MODELS_DIR");

  await ensureDir(stateDir);
  await ensureDir(workspaceDir);
  await ensureDir(logsDir);

  process.env.OPENCLAW_STATE_DIR = stateDir;
  process.env.OPENCLAW_CONFIG_PATH = configPath;
  process.env.OPENCLAW_GATEWAY_PORT = String(gatewayPort);
  process.env.VLLM_API_KEY = normalizeString(process.env.VLLM_API_KEY) || "vllm-local";
  ensurePnpmShim();

  const liveModelIds = await ensureLlamaRunning(
    llamaExe,
    modelsDir,
    llamaLogPath,
    extraArgs,
    gpuLayers,
  );
  await bootstrapConfig(configPath, workspaceDir, liveModelIds, defaultModelOverride);
  await ensureGatewayRunning(ROOT_DIR, gatewayPort, gatewayLogPath);
}

main().catch((error) => {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`Agent-02 launcher failed: ${message}`);
  process.exitCode = 1;
});
