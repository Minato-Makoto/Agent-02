---
title: "Windows Setup"
description: "Prepare the Windows environment, local llama.cpp binaries, and first build for Agent-02."
---

# Windows Setup

[Vietnamese version](../vi/windows-setup)

## Prerequisites

- Windows with PowerShell available
- Node.js 22 or newer
- `corepack` in `PATH`
- `llama-server.exe` available at `..\\llama.cpp\\llama-server.exe` or overridden in `run.local.bat`
- `.gguf` models available at `..\\models\\` or overridden in `run.local.bat`

## First Start

1. Open `run.local.bat` only if you need local overrides.
2. Double-click `run.bat`.
3. On the first run, the launcher installs dependencies and builds the project automatically.
4. After the stack is healthy, the dashboard opens in the browser.

## Build Commands

If you want to build manually:

```powershell
corepack pnpm install
corepack pnpm ui:build
corepack pnpm build
```

## What This Repo No Longer Supports

- Android build/install flows
- iOS/macOS Xcode and signing flows
- Docker and cloud deployment packaging
