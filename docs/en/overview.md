---
title: "Overview"
description: "What Agent-02 is, what it keeps, and what was intentionally removed from the upstream mirror."
---

# Overview

[Vietnamese version](../vi/overview)

Agent-02 is a Windows-only local AI workstation built on the OpenClaw core.

The supported runtime is:

- `run.bat` for startup
- `run.local.bat` for local overrides
- `.openclaw/` for config, logs, workspace, and runtime state
- `llama-server` on `127.0.0.1:8000`
- OpenClaw gateway/dashboard on `127.0.0.1:18789`

This fork keeps:

- the TypeScript core
- the browser dashboard
- the local `llama-server` integration path
- the Canvas/A2UI build path that is still required by the current build

This fork removes:

- Android, iOS, and macOS native app surfaces
- Docker and container packaging
- release/distribution automation
- upstream locale docs outside English and Vietnamese

Next:

- [Windows setup](./windows-setup)
- [Launcher and overrides](./launcher)
- [Model selection](./models)
