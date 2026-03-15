---
title: Agent-02 Installer Blueprint for OpenClaw and llama.cpp
description: Windows-only blueprint for the docs-only installer that mirrors OpenClaw source and generates thin launchers for llama-server.
---

# Agent-02 Installer Blueprint for OpenClaw and llama.cpp

## Goal

Agent-02 is a docs-only installer workspace with one clear split:

- The tracked repo contains only docs, skills, and the installer script.
- The installer mirrors a user-owned OpenClaw source checkout into `.agent02-local/openclaw/`, builds it, and generates thin launchers.
- `llama-server.exe` from llama.cpp is treated as an external OpenAI-compatible model server on a fixed port (`127.0.0.1:8420`).
- Provider setup remains manual inside OpenClaw. The launcher prints connection details but never writes provider config.

## Install path chosen

Source-mirror OpenClaw, not the public `install.ps1` installer:

1. User fills `install.local.bat` with paths to their existing OpenClaw source checkout and `llama-server.exe`.
2. User runs `scripts/install-openclaw.ps1`.
3. The script validates prerequisites, mirrors and builds OpenClaw, then generates launchers and local docs under `.agent02-local/`.
4. Services are never started during install.

## Ownership boundary

### OpenClaw owns

- gateway bind, port, auth token, and daemon lifecycle
- Control UI and dashboard access
- agent sessions, routing, tool use, and usage tracking
- channel login and channel credentials
- node or device pairing and approvals
- web tools, plugins, and optional OpenProse integration
- provider config written under the OpenClaw state directory

### llama.cpp owns

- loading one or more GGUF models
- exposing `/v1/models` (requires `Authorization: Bearer <key>`)
- serving `/v1/chat/completions`
- exposing `/health` (public, no auth required)
- enforcing the API key for all other endpoints

### The repo does not own

- default provider API keys
- default model ids
- hidden provider catalogs
- writes into `%USERPROFILE%\.openclaw\openclaw.json`
- writes into agent-local `models.json`

## Config surface

All user config lives in `install.local.bat` (git-ignored). A tracked example is provided at `install.local.bat.example`.
The generated launchers re-read `install.local.bat` at runtime, so changing
runtime values does not require reinstalling.

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENCLAW_SOURCE_DIR` | Yes | — | Absolute path to OpenClaw source checkout |
| `LLAMA_SERVER_EXE` | Yes | — | Absolute path to `llama-server.exe` |
| `MODEL_PATH` | No | — | Default `.gguf` path; launcher can also accept this as arg 1 or prompt |
| `LLAMA_SERVER_API_KEY` | No | `agent02-local` | Bearer token for llama-server auth |
| `OPENCLAW_PORT` | No | `18789` | Port for the OpenClaw gateway |
| `OPENCLAW_NO_OPEN` | No | `0` | Set to `1` to suppress auto-opening the dashboard |
| `EXTRA_LLAMA_ARGS` | No | — | Extra flags for llama-server (must not override `-m`, `--host`, `--port`, `--api-key`) |

## Install flow

### Step 1: Fill config

Copy `install.local.bat.example` to `install.local.bat` and set your paths:

```bat
set "OPENCLAW_SOURCE_DIR=D:\AI-Agent\openclaw-2026.3.12"
set "LLAMA_SERVER_EXE=D:\AI-Agent\llama.cpp\llama-server.exe"
```

### Step 2: Run the installer

```powershell
powershell -File scripts\install-openclaw.ps1
```

The installer:

1. Validates Node.js >= 22, pnpm (or corepack pnpm), the OpenClaw source shape, and the llama-server binary.
2. Rejects reserved flags inside `EXTRA_LLAMA_ARGS` (`-m`, `--host`, `--port`, `--api-key`, `--api-key-file`).
3. Runs `robocopy /MIR` from `OPENCLAW_SOURCE_DIR` to `.agent02-local/openclaw/` with excludes for `.git`, `node_modules`, `dist`, `.openclaw`, caches, temp files, and logs.
4. Runs `pnpm install` in the mirror.
5. Runs `pnpm openclaw setup` only when `%USERPROFILE%\.openclaw\openclaw.json` is missing.
6. Runs `pnpm build`.
7. Generates launchers in `.agent02-local/launcher/` and usage docs in `.agent02-local/docs/`.

### What install does NOT do

- Start llama-server or the OpenClaw gateway
- Require `MODEL_PATH` to be set
- Write any OpenClaw provider config
- Create runtime state directories (those are created lazily on first run)

## Runtime flow

### Starting

Run the generated launcher:

```bat
.agent02-local\launcher\run-agent02.bat D:\Models\your-model.gguf
```

Model path resolution:
1. First argument to `run-agent02.bat`
2. Fall back to `MODEL_PATH` from `install.local.bat`
3. Prompt the user if neither is available

The launcher:
1. Re-reads `install.local.bat` at runtime.
2. Starts `llama-server.exe -m <gguf> --host 127.0.0.1 --port 8420 --api-key <key> [EXTRA_LLAMA_ARGS]`
3. Writes runtime PID files, metadata, and logs only under `.agent02-local/runtime/`
4. Polls `/health` until the server reports healthy (up to 120 seconds)
5. Calls authenticated `GET /v1/models` and requires at least one model id
6. Starts `pnpm openclaw gateway --port <OPENCLAW_PORT> --bind loopback`
7. Uses `pnpm openclaw dashboard` / `pnpm openclaw dashboard --no-open` to print or open the dashboard URL
8. Prints the base URL, API key, model id(s), dashboard URL, and log paths

### Stopping

```bat
.agent02-local\launcher\stop-agent02.bat
```

Kills only the tracked process trees rooted at the stored PID/metadata in `.agent02-local/runtime/`.

## Provider setup

After the launcher prints the connection details, register the model inside OpenClaw manually:

| Field | Value |
|---|---|
| Base URL | `http://127.0.0.1:8420/v1` |
| API key | the configured `LLAMA_SERVER_API_KEY` |
| Model id | the id(s) printed at startup |

You can do this through:
- The OpenClaw dashboard (Control UI)
- `pnpm openclaw configure`
- `pnpm openclaw onboard`

Existing cloud providers in OpenClaw remain untouched because the launcher does not rewrite OpenClaw config.

## Forbidden drift

Do not reintroduce any of the following:

- a launcher that injects `VLLM_API_KEY` or equivalent provider state behind OpenClaw's back
- `MODEL_PATH`, `DEFAULT_MODEL_ID`, or `MODELS_DIR` as policy layers that select models for OpenClaw
- auto-generated writes into OpenClaw config from repo scripts
- direct channel, node, or dashboard traffic to `llama-server.exe`
- storing the gateway token inside the llama.cpp startup command
- binding either service to a public interface before auth is intentionally configured
- generated launchers that call back into the installer

## Validation checklist

1. `scripts/install-openclaw.ps1` completes without errors.
2. `.agent02-local/openclaw/` contains a built OpenClaw mirror.
3. `.agent02-local/launcher/run-agent02.bat` and `stop-agent02.bat` exist.
4. `.agent02-local/docs/usage.en.md` and `usage.vi.md` exist.
5. `run-agent02.bat <model.gguf>` starts llama-server and prints `/health` ok.
6. Authenticated `/v1/models` on port 8420 returns the loaded model id.
7. OpenClaw gateway starts on the configured port.
8. Printed values exactly match `http://127.0.0.1:8420/v1`, the API key, and the model id(s).
9. Manual provider setup in OpenClaw works with the printed values.
10. Existing cloud models remain untouched.
11. `stop-agent02.bat` kills only tracked PIDs.
12. `node scripts/check-docs-parity.mjs` passes.

## Source anchors

OpenClaw references:

- Source setup: https://docs.openclaw.ai/start/setup
- Gateway CLI: https://docs.openclaw.ai/cli/gateway
- Control UI: https://docs.openclaw.ai/web/control-ui
- vLLM provider: https://docs.openclaw.ai/providers/vllm
- Source anchor: `src/commands/self-hosted-provider-setup.ts`
- Source anchor: `extensions/vllm/index.ts`
- Source anchor: `src/commands/dashboard.ts`

llama.cpp references:

- Server guide: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
- Build guide: https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md
- REST API changelog: https://github.com/ggml-org/llama.cpp/issues/9291

Key llama-server details (from `llama-knowledge` skill):

- `--api-key` enables bearer auth for all endpoints except `/health`
- `/health` is always public
- `/v1/models` requires `Authorization: Bearer <key>` when `--api-key` is set
- The fixed port `8420` is an Agent-02 convention, not a llama.cpp default
