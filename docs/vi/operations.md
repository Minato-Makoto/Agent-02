---
title: "Vận Hành"
description: "Khởi động, restart, quan sát và tắt hoàn toàn local Agent-02 stack."
---

# Vận Hành

[English version](../en/operations)

## URL

- Dashboard: `http://127.0.0.1:18789/`
- API của `llama-server`: `http://127.0.0.1:8000/v1`
- Web UI của `llama.cpp` khi cần debug: `http://127.0.0.1:8000/`

## Log và State

- State directory: `.openclaw/`
- Log: `.openclaw/logs/`
- Config: `.openclaw/openclaw.json`

## Tắt Hoàn Toàn

Đóng browser là chưa đủ. Ưu tiên dùng `stop.bat` để tắt hết stack local.

PowerShell fallback thủ công:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8000,18789 -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique |
  ForEach-Object { Stop-Process -Id $_ -Force }
```

## Restart

- chạy `stop.bat`
- chạy lại `run.bat`
