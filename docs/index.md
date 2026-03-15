---
title: Agent-02 Docs-Only Installer
description: Docs-only installer workspace for OpenClaw source mirroring and llama-server local provider launchers on Windows.
---

# Agent-02 Docs-Only Installer

This workspace tracks only docs, skills, and the installer script. All installed runtime state stays under `.agent02-local/` or the default OpenClaw user state.

- English blueprint: [/en/openclaw-llama-blueprint](/en/openclaw-llama-blueprint)
- Vietnamese blueprint: [/vi/openclaw-llama-blueprint](/vi/openclaw-llama-blueprint)

## How it works

1. Copy `install.local.bat.example` → `install.local.bat` with your paths.
2. Run `powershell -File scripts\install-openclaw.ps1`.
3. Installer mirrors/builds OpenClaw and generates launchers plus local usage docs under `.agent02-local/`.
4. Start `run-agent02.bat <model.gguf>` from the generated launcher directory.
5. Register the model in OpenClaw using the printed connection details.

The generated launchers re-read `install.local.bat` at runtime.
Runtime logs and PID files are created lazily under `.agent02-local/runtime/`.
