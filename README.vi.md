# Agent-02

Workspace docs-only installer để chạy OpenClaw với llama.cpp làm model server local trên Windows.

## Repo này chứa gì

- `scripts/install-openclaw.ps1` — điểm vào cài đặt duy nhất được hỗ trợ
- `install.local.bat.example` — mẫu config (copy sang `install.local.bat` rồi điền đường dẫn của bạn)
- `docs/` — blueprint song ngữ (EN + VI) giải thích kiến trúc và cách setup provider
- `install-openclaw/` — skill: source setup OpenClaw, flow gateway/dashboard, luật ranh giới provider
- `llama-knowledge/` — skill: cờ llama-server, `/health`, `/v1/models`, chi tiết runtime Windows

## Repo này KHÔNG chứa gì

- Không có OpenClaw checkout được commit (source được mirror lúc chạy vào `.agent02-local/openclaw/`)
- Không có launcher đã tạo (được installer tạo dưới `.agent02-local/launcher/`)
- Không có runtime state (PID file và log nằm dưới `.agent02-local/runtime/`, tạo lazy khi chạy lần đầu)

## Runtime config surface

`install.local.bat` là file do user sở hữu và bị git-ignore.

- Installer sẽ đọc file này.
- Launcher đã tạo cũng đọc lại file này ở runtime.
- Khi đổi `MODEL_PATH`, `LLAMA_SERVER_API_KEY`, `OPENCLAW_PORT`, `OPENCLAW_NO_OPEN`, hoặc `EXTRA_LLAMA_ARGS`, bạn không cần tạo lại launcher.

## Bắt đầu nhanh

1. Copy `install.local.bat.example` sang `install.local.bat` và đặt đường dẫn:

   ```bat
   set "OPENCLAW_SOURCE_DIR=D:\duong-dan\den\openclaw-source"
   set "LLAMA_SERVER_EXE=D:\duong-dan\den\llama-server.exe"
   ```

2. Chạy installer:

   ```powershell
   powershell -File scripts\install-openclaw.ps1
   ```

   Install sẽ mirror và build OpenClaw, rồi tạo launcher và usage docs local.
   Nó không bao giờ tự khởi động `llama-server` hay OpenClaw gateway.

3. Khởi động launcher với model:

   ```bat
   .agent02-local\launcher\run-agent02.bat D:\Models\model-cua-ban.gguf
   ```

4. Dùng các giá trị được in ra để đăng ký model làm provider trong OpenClaw.

Log runtime và PID/metadata chỉ được tạo dưới `.agent02-local/runtime/`.

## Blueprint

- English: [docs/en/openclaw-llama-blueprint.md](docs/en/openclaw-llama-blueprint.md)
- Tiếng Việt: [docs/vi/openclaw-llama-blueprint.md](docs/vi/openclaw-llama-blueprint.md)
