# Agent-02

Docs-only installer workspace for running OpenClaw with llama.cpp as a local model server on Windows.

## What this repo contains

- `scripts/install-openclaw.ps1` — the only supported install entrypoint
- `install.local.bat.example` — config template (copy to `install.local.bat` and fill in your paths)
- `docs/` — bilingual blueprint (EN + VI) explaining the architecture and provider setup
- `install-openclaw/` — skill: OpenClaw source setup, gateway/dashboard flow, provider-boundary rules
- `llama-knowledge/` — skill: llama-server flags, `/health`, `/v1/models`, Windows runtime details

## What this repo does NOT contain

- No committed OpenClaw checkout (source is mirrored at runtime into `.agent02-local/openclaw/`)
- No generated launchers (created by the installer under `.agent02-local/launcher/`)
- No runtime state (PID files and logs live under `.agent02-local/runtime/`, created lazily on first run)

## Runtime config surface

`install.local.bat` is user-owned and git-ignored.

- The installer reads it.
- Generated launchers read it again at runtime.
- Changing `MODEL_PATH`, `LLAMA_SERVER_API_KEY`, `OPENCLAW_PORT`, `OPENCLAW_NO_OPEN`, or `EXTRA_LLAMA_ARGS` does not require regenerating launchers.

## Quick start

1. Copy `install.local.bat.example` to `install.local.bat` and set your paths:

   ```bat
   set "OPENCLAW_SOURCE_DIR=D:\path\to\openclaw-source"
   set "LLAMA_SERVER_EXE=D:\path\to\llama-server.exe"
   ```

2. Run the installer:

   ```powershell
   powershell -File scripts\install-openclaw.ps1
   ```

   Install mirrors and builds OpenClaw, then generates launchers and local usage docs.
   It never starts `llama-server` or the OpenClaw gateway.

3. Start the launcher with a model:

   ```bat
   .agent02-local\launcher\run-agent02.bat D:\Models\your-model.gguf
   ```

4. Use the printed values to register the model as a provider inside OpenClaw.

Runtime logs and PID/metadata files are created only under `.agent02-local/runtime/`.

## Blueprint

- English: [docs/en/openclaw-llama-blueprint.md](docs/en/openclaw-llama-blueprint.md)
- Tiếng Việt: [docs/vi/openclaw-llama-blueprint.md](docs/vi/openclaw-llama-blueprint.md)
