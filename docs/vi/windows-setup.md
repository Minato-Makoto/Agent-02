---
title: "Windows Setup"
description: "Chuẩn bị môi trường Windows, binary llama.cpp local và build đầu tiên cho Agent-02."
---

# Windows Setup

[English version](../en/windows-setup)

## Điều Kiện Cần

- Windows có PowerShell
- Node.js 22 trở lên
- `corepack` có trong `PATH`
- `llama-server.exe` nằm ở `..\\llama.cpp\\llama-server.exe` hoặc được override trong `run.local.bat`
- model `.gguf` nằm ở `..\\models\\` hoặc được override trong `run.local.bat`

## Chạy Lần Đầu

1. Mở `run.local.bat` nếu cần override local.
2. Double-click `run.bat`.
3. Lần chạy đầu tiên launcher sẽ tự cài dependencies và build project.
4. Khi stack healthy, dashboard sẽ tự mở trong browser.

## Lệnh Build Thủ Công

Nếu muốn build thủ công:

```powershell
corepack pnpm install
corepack pnpm ui:build
corepack pnpm build
```

## Những Surface Không Còn Hỗ Trợ

- Android build/install flows
- iOS/macOS Xcode và signing flows
- Docker và cloud deployment packaging
