---
title: "Troubleshooting"
description: "Common startup and runtime failures in the Windows-only Agent-02 fork."
---

# Troubleshooting

[Vietnamese version](../vi/troubleshooting)

## `node` or `corepack` not found

Install Node.js 22+ and reopen the terminal or Explorer session before launching again.

## Port `8000` is busy

Another process is already listening on the `llama-server` port. Stop that process or free the port before launching Agent-02.

## Port `18789` is busy

Another process is already using the OpenClaw gateway/dashboard port. Stop it before launching Agent-02.

## `/v1/models` is empty

No valid `.gguf` models were discovered in `MODELS_DIR`. Add models to the directory and relaunch.

## `openclaw.json` is invalid

Fix `.openclaw/openclaw.json` if it was edited manually and contains invalid JSON. The launcher intentionally refuses to overwrite a broken config file.

## Build is missing

Run:

```powershell
corepack pnpm install
corepack pnpm ui:build
corepack pnpm build
```
