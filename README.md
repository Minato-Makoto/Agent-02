# Agent-02

Agent-02 is a Windows-only local AI workstation built on the OpenClaw core and a local `llama-server` process.

It keeps the current runtime contract:

- `run.bat` is the primary launcher.
- `stop.bat` is the primary shutdown helper.
- `run.local.bat` is the local override layer.
- `.openclaw/` stores config, logs, workspace, and runtime state.
- `llama-server` listens on `127.0.0.1:8000`.
- the OpenClaw gateway and dashboard listen on `127.0.0.1:18789`.

This fork intentionally removes mobile, macOS, Docker, and release-distribution surfaces so the repo stays focused on the Windows local workflow.

## Documentation

- English docs: [docs/en/overview.md](docs/en/overview.md)
- Vietnamese docs: [README.vi.md](README.vi.md) and [docs/vi/overview.md](docs/vi/overview.md)

## Quick Start

1. Install Node.js 22+ and make sure `node` and `corepack` are in `PATH`.
2. Place `llama-server.exe` in `..\\llama.cpp\\`.
3. Place `.gguf` model files in `..\\models\\`.
4. Adjust [run.local.bat](run.local.bat) if you want to override model selection, GPU layers, ports, or paths.
5. Double-click [run.bat](run.bat) to start the stack.
6. Double-click [stop.bat](stop.bat) when you want a full shutdown.

On the first run, the launcher installs dependencies and builds the project automatically when `dist/entry.js` is missing.

## Model Selection

Agent-02 does not hardcode a context window or output token limit in the launcher.

- If `DEFAULT_MODEL_ID` is set in [run.local.bat](run.local.bat), that model becomes the default Agent-02 model.
- If `DEFAULT_MODEL_ID` is empty, the launcher reads `GET /v1/models` from `llama-server` and picks the first model ID in stable alphabetical order.
- OpenClaw then uses `vllm/<model-id>` as the default primary model.

## Operations

- Dashboard: `http://127.0.0.1:18789/`
- `llama-server` API: `http://127.0.0.1:8000/v1`
- Optional `llama.cpp` Web UI: `http://127.0.0.1:8000/`
- Logs: `.openclaw/logs/`

To shut everything down completely, prefer [stop.bat](stop.bat).

Manual PowerShell fallback:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8000,18789 -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique |
  ForEach-Object { Stop-Process -Id $_ -Force }
```

## Repo Scope

This repo keeps:

- the OpenClaw TypeScript core and UI
- the current Windows launcher flow
- the local model integration path through `llama-server`
- the Canvas/A2UI build path still required by the current build

This repo removes:

- Android, iOS, and macOS native app surfaces
- Docker and container packaging flows
- release automation and maintainer packaging baggage
- locale docs other than English and Vietnamese
