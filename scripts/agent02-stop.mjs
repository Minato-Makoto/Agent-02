#!/usr/bin/env node

import { spawnSync } from "node:child_process";

const LLAMA_PORT = 8000;

function normalizeString(value) {
  if (typeof value !== "string") {
    return "";
  }
  return value.trim();
}

function parseInteger(value, fallback) {
  const trimmed = normalizeString(value);
  if (!trimmed) {
    return fallback;
  }
  const parsed = Number.parseInt(trimmed, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
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

function stopPid(pid) {
  const result = spawnSync("taskkill.exe", ["/PID", String(pid), "/T", "/F"], {
    encoding: "utf8",
    windowsHide: true,
  });

  if (result.error) {
    throw result.error;
  }

  if (result.status !== 0) {
    const stderr = normalizeString(result.stderr);
    const stdout = normalizeString(result.stdout);
    throw new Error(stderr || stdout || `taskkill exited with code ${result.status}`);
  }
}

function stopKnownPort(port, validator, label) {
  const pids = getListeningPids(port);
  if (pids.length === 0) {
    console.log(`${label}: already stopped on port ${port}.`);
    return 0;
  }

  let stopped = 0;
  for (const pid of pids) {
    const info = getProcessInfo(pid);
    const validationError = validator(info, pid);
    if (validationError) {
      throw new Error(validationError);
    }
    stopPid(pid);
    stopped += 1;
    console.log(`${label}: stopped PID ${pid} on port ${port}.`);
  }

  return stopped;
}

function validateLlamaProcess(info, pid) {
  const name = normalizeString(info?.Name).toLowerCase();
  if (name !== "llama-server.exe") {
    return `Port ${LLAMA_PORT} is owned by ${info?.Name ?? `PID ${pid}`}, not llama-server.exe. Refusing to stop it.`;
  }
  return "";
}

function validateGatewayProcess(port) {
  return (info, pid) => {
    const commandLine = normalizeString(info?.CommandLine);
    if (!/openclaw\.mjs/i.test(commandLine) || !/\bgateway\b/i.test(commandLine)) {
      return `Port ${port} is owned by ${info?.Name ?? `PID ${pid}`}, not an OpenClaw gateway process. Refusing to stop it.`;
    }
    return "";
  };
}

function main() {
  const gatewayPort = parseInteger(
    process.env.GATEWAY_PORT ?? process.env.OPENCLAW_GATEWAY_PORT,
    18789,
  );

  const llamaStopped = stopKnownPort(LLAMA_PORT, validateLlamaProcess, "llama-server");
  const gatewayStopped = stopKnownPort(
    gatewayPort,
    validateGatewayProcess(gatewayPort),
    "openclaw-gateway",
  );

  if (llamaStopped === 0 && gatewayStopped === 0) {
    console.log("Agent-02: nothing was running.");
    return;
  }

  console.log("Agent-02: shutdown complete.");
}

try {
  main();
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`Agent-02 stop failed: ${message}`);
  process.exitCode = 1;
}
