---
title: "Launcher and Overrides"
description: "How run.bat and run.local.bat work in the Windows-only Agent-02 fork."
---

# Launcher and Overrides

[Vietnamese version](../vi/launcher)

`run.bat` is the only primary entrypoint for operators.

It performs these steps:

1. load `run.local.bat` if it exists
2. install dependencies when `node_modules` is missing
3. build UI and runtime when `dist/entry.js` is missing
4. start or reuse `llama-server`
5. start or reuse the OpenClaw gateway
6. open the dashboard

## Supported Local Overrides

Edit `run.local.bat` to override:

- `LLAMA_SERVER_EXE`
- `MODELS_DIR`
- `DEFAULT_MODEL_ID`
- `GPU_LAYERS`
- `GATEWAY_PORT`
- `OPENCLAW_STATE_DIR`
- `OPEN_LLAMA_UI`
- `EXTRA_LLAMA_ARGS`

## Invariants

- `LLAMA_PORT` stays fixed at `8000`
- the launcher does not force `--ctx-size`
- the launcher does not force `--n-predict`
- local state stays under `.openclaw/`
