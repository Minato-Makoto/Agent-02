---
title: "Tổng Quan"
description: "Agent-02 là gì, giữ lại gì, và đã bỏ gì so với mirror upstream."
---

# Tổng Quan

[English version](../en/overview)

Agent-02 là trạm AI local chỉ dành cho Windows, được xây trên OpenClaw core.

Runtime được support:

- `run.bat` để khởi động
- `run.local.bat` để override local
- `.openclaw/` để chứa config, log, workspace và runtime state
- `llama-server` trên `127.0.0.1:8000`
- OpenClaw gateway/dashboard trên `127.0.0.1:18789`

Fork này giữ:

- TypeScript core
- browser dashboard
- local `llama-server` integration path
- Canvas/A2UI build path đang cần cho build hiện tại

Fork này bỏ:

- native app surface của Android, iOS và macOS
- Docker và container packaging
- release/distribution automation
- docs locale upstream ngoài English và Vietnamese

Tiếp theo:

- [Windows setup](./windows-setup)
- [Launcher và local overrides](./launcher)
- [Model selection](./models)
