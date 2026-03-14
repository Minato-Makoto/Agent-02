---
title: "Operations"
description: "Start, restart, inspect, and fully shut down the local Agent-02 stack."
---

# Operations

[Vietnamese version](../vi/operations)

## URLs

- Dashboard: `http://127.0.0.1:18789/`
- `llama-server` API: `http://127.0.0.1:8000/v1`
- Optional `llama.cpp` Web UI: `http://127.0.0.1:8000/`

## Logs and State

- State directory: `.openclaw/`
- Logs: `.openclaw/logs/`
- Config: `.openclaw/openclaw.json`

## Full Shutdown

Closing the browser is not enough. Prefer `stop.bat` for a full local shutdown.

Manual PowerShell fallback:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8000,18789 -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique |
  ForEach-Object { Stop-Process -Id $_ -Force }
```

## Restart

- run `stop.bat`
- launch `run.bat` again
