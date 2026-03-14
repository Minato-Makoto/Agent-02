---
title: "Troubleshooting"
description: "Các lỗi startup và runtime thường gặp trong fork Windows-only của Agent-02."
---

# Troubleshooting

[English version](../en/troubleshooting)

## Không tìm thấy `node` hoặc `corepack`

Cài Node.js 22+ rồi mở lại terminal hoặc Explorer session trước khi chạy lại launcher.

## Port `8000` đang bị chiếm

Đang có process khác lắng nghe ở port của `llama-server`. Hãy tắt process đó hoặc giải phóng port rồi chạy lại Agent-02.

## Port `18789` đang bị chiếm

Đang có process khác dùng port gateway/dashboard của OpenClaw. Hãy tắt nó trước khi chạy Agent-02.

## `/v1/models` rỗng

Không có `.gguf` hợp lệ nào được tìm thấy trong `MODELS_DIR`. Thêm model vào thư mục rồi chạy lại.

## `openclaw.json` bị lỗi

Nếu `.openclaw/openclaw.json` bị sửa tay và sai JSON, hãy sửa file đó. Launcher có chủ đích không ghi đè một config đang bị hỏng.

## Build chưa có

Chạy:

```powershell
corepack pnpm install
corepack pnpm ui:build
corepack pnpm build
```
