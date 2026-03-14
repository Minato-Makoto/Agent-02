---
title: "Launcher và Overrides"
description: "run.bat và run.local.bat hoạt động như thế nào trong fork Windows-only của Agent-02."
---

# Launcher và Overrides

[English version](../en/launcher)

`run.bat` là entrypoint chính duy nhất cho operator.

Nó làm các bước sau:

1. load `run.local.bat` nếu tồn tại
2. cài dependencies khi `node_modules` chưa có
3. build UI và runtime khi `dist/entry.js` chưa có
4. start hoặc reuse `llama-server`
5. start hoặc reuse OpenClaw gateway
6. mở dashboard

## Các Local Override Được Hỗ Trợ

Chỉnh `run.local.bat` để override:

- `LLAMA_SERVER_EXE`
- `MODELS_DIR`
- `DEFAULT_MODEL_ID`
- `GPU_LAYERS`
- `GATEWAY_PORT`
- `OPENCLAW_STATE_DIR`
- `OPEN_LLAMA_UI`
- `EXTRA_LLAMA_ARGS`

## Các Invariant

- `LLAMA_PORT` cố định là `8000`
- launcher không ép `--ctx-size`
- launcher không ép `--n-predict`
- local state luôn nằm trong `.openclaw/`
