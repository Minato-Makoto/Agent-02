---
title: Blueprint Installer Agent-02 cho OpenClaw và llama.cpp
description: Blueprint chỉ dành cho Windows cho docs-only installer mirror source OpenClaw và tạo thin launcher cho llama-server.
---

# Blueprint Installer Agent-02 cho OpenClaw và llama.cpp

## Mục tiêu

Agent-02 là workspace docs-only installer với một ranh giới rõ ràng:

- Repo tracked chỉ chứa docs, skills, và script installer.
- Installer mirror source checkout OpenClaw do user sở hữu vào `.agent02-local/openclaw/`, build nó, rồi tạo thin launcher.
- `llama-server.exe` của llama.cpp được coi là model server OpenAI-compatible bên ngoài trên port cố định (`127.0.0.1:8420`).
- Việc setup provider luôn là thủ công trong OpenClaw. Launcher in ra thông tin kết nối nhưng không bao giờ ghi provider config.

## Install path được chọn

Source-mirror OpenClaw, không phải `install.ps1` công khai:

1. User điền `install.local.bat` với đường dẫn đến OpenClaw source checkout và `llama-server.exe` hiện có.
2. User chạy `scripts/install-openclaw.ps1`.
3. Script validate prerequisites, mirror và build OpenClaw, rồi tạo launcher và docs local dưới `.agent02-local/`.
4. Không bao giờ khởi động service trong lúc install.

## Boundary ownership

### OpenClaw sở hữu

- bind, port, auth token và vòng đời daemon của gateway
- quyền truy cập Control UI và dashboard
- session agent, routing, gọi tool và usage tracking
- channel login và credentials của channel
- pairing node hoặc device và approval
- web tools, plugin và tích hợp OpenProse nếu cần
- provider config được ghi trong state directory của OpenClaw

### llama.cpp sở hữu

- nạp một hoặc nhiều model GGUF
- expose `/v1/models` (cần `Authorization: Bearer <key>`)
- phục vụ `/v1/chat/completions`
- expose `/health` (công khai, không cần auth)
- enforce API key cho tất cả endpoint khác

### Repo không được sở hữu

- API key provider mặc định
- model id mặc định
- catalog provider ẩn
- ghi vào `%USERPROFILE%\.openclaw\openclaw.json`
- ghi vào `models.json` ở agent local

## Config surface

Toàn bộ config user nằm trong `install.local.bat` (git-ignored). Mẫu tracked có tại `install.local.bat.example`.
Launcher được tạo sẽ đọc lại `install.local.bat` ở runtime, nên khi đổi
giá trị runtime bạn không cần cài lại.

| Biến | Bắt buộc | Mặc định | Mô tả |
|---|---|---|---|
| `OPENCLAW_SOURCE_DIR` | Có | — | Đường dẫn tuyệt đối đến OpenClaw source checkout |
| `LLAMA_SERVER_EXE` | Có | — | Đường dẫn tuyệt đối đến `llama-server.exe` |
| `MODEL_PATH` | Không | — | Đường dẫn `.gguf` mặc định; launcher cũng nhận qua arg 1 hoặc hỏi user |
| `LLAMA_SERVER_API_KEY` | Không | `agent02-local` | Bearer token cho auth llama-server |
| `OPENCLAW_PORT` | Không | `18789` | Port cho OpenClaw gateway |
| `OPENCLAW_NO_OPEN` | Không | `0` | Đặt `1` để không tự mở dashboard |
| `EXTRA_LLAMA_ARGS` | Không | — | Cờ thêm cho llama-server (không được ghi đè `-m`, `--host`, `--port`, `--api-key`) |

## Flow cài đặt

### Bước 1: Điền config

Copy `install.local.bat.example` sang `install.local.bat` và đặt đường dẫn:

```bat
set "OPENCLAW_SOURCE_DIR=D:\AI-Agent\openclaw-2026.3.12"
set "LLAMA_SERVER_EXE=D:\AI-Agent\llama.cpp\llama-server.exe"
```

### Bước 2: Chạy installer

```powershell
powershell -File scripts\install-openclaw.ps1
```

Installer sẽ:

1. Validate Node.js >= 22, pnpm (hoặc corepack pnpm), hình dáng OpenClaw source, và binary llama-server.
2. Từ chối các cờ reserved nằm trong `EXTRA_LLAMA_ARGS` (`-m`, `--host`, `--port`, `--api-key`, `--api-key-file`).
3. Chạy `robocopy /MIR` từ `OPENCLAW_SOURCE_DIR` vào `.agent02-local/openclaw/` với các loại trừ `.git`, `node_modules`, `dist`, `.openclaw`, cache, file tạm và log.
4. Chạy `pnpm install` trong bản mirror.
5. Chạy `pnpm openclaw setup` chỉ khi `%USERPROFILE%\.openclaw\openclaw.json` chưa tồn tại.
6. Chạy `pnpm build`.
7. Tạo launcher trong `.agent02-local/launcher/` và docs sử dụng trong `.agent02-local/docs/`.

### Install KHÔNG làm gì

- Khởi động llama-server hoặc OpenClaw gateway
- Yêu cầu `MODEL_PATH` phải được đặt
- Ghi bất kỳ provider config nào của OpenClaw
- Tạo thư mục runtime state (được tạo lazy khi chạy lần đầu)

## Flow runtime

### Khởi động

Chạy launcher đã được tạo:

```bat
.agent02-local\launcher\run-agent02.bat D:\Models\model-cua-ban.gguf
```

Cách xác định model path:
1. Tham số đầu tiên của `run-agent02.bat`
2. Fallback về `MODEL_PATH` từ `install.local.bat`
3. Hỏi user nếu cả hai đều không có

Launcher sẽ:
1. Đọc lại `install.local.bat` ở runtime.
2. Khởi động `llama-server.exe -m <gguf> --host 127.0.0.1 --port 8420 --api-key <key> [EXTRA_LLAMA_ARGS]`
3. Ghi PID, metadata, và log runtime chỉ dưới `.agent02-local/runtime/`
4. Poll `/health` cho đến khi server báo healthy (tối đa 120 giây)
5. Gọi authenticated `GET /v1/models` và yêu cầu có ít nhất một model id
6. Khởi động `pnpm openclaw gateway --port <OPENCLAW_PORT> --bind loopback`
7. Dùng `pnpm openclaw dashboard` / `pnpm openclaw dashboard --no-open` để in hoặc mở dashboard URL
8. In ra base URL, API key, model id, dashboard URL, và đường dẫn log

### Dừng

```bat
.agent02-local\launcher\stop-agent02.bat
```

Chỉ tắt process tree gốc từ PID/metadata đang được theo dõi trong `.agent02-local/runtime/`.

## Setup provider

Sau khi launcher in ra thông tin kết nối, đăng ký model trong OpenClaw thủ công:

| Trường | Giá trị |
|---|---|
| Base URL | `http://127.0.0.1:8420/v1` |
| API key | `LLAMA_SERVER_API_KEY` đã cấu hình |
| Model id | id được in ra lúc khởi động |

Bạn có thể làm qua:
- Dashboard OpenClaw (Control UI)
- `pnpm openclaw configure`
- `pnpm openclaw onboard`

Các provider cloud hiện có trong OpenClaw không bị ảnh hưởng vì launcher không ghi lại config OpenClaw.

## Drift bị cấm

Không được đưa lại bất kỳ điều nào sau đây:

- launcher tự inject `VLLM_API_KEY` hoặc provider state tương đương sau lưng OpenClaw
- `MODEL_PATH`, `DEFAULT_MODEL_ID`, hoặc `MODELS_DIR` như policy layer chọn model cho OpenClaw
- script trong repo tự ghi config vào OpenClaw
- channel, node, hoặc dashboard đi trực tiếp tới `llama-server.exe`
- nhét gateway token vào lệnh startup của llama.cpp
- bind bất kỳ service nào ra public interface trước khi auth được cấu hình có chủ đích
- launcher đã tạo gọi ngược lại installer

## Checklist xác minh

1. `scripts/install-openclaw.ps1` hoàn tất không lỗi.
2. `.agent02-local/openclaw/` chứa bản mirror OpenClaw đã build.
3. `.agent02-local/launcher/run-agent02.bat` và `stop-agent02.bat` tồn tại.
4. `.agent02-local/docs/usage.en.md` và `usage.vi.md` tồn tại.
5. `run-agent02.bat <model.gguf>` khởi động llama-server và in `/health` ok.
6. Authenticated `/v1/models` trên port 8420 trả về model id đã load.
7. OpenClaw gateway khởi động trên port đã cấu hình.
8. Giá trị in ra khớp chính xác `http://127.0.0.1:8420/v1`, API key, và model id.
9. Setup provider thủ công trong OpenClaw hoạt động với giá trị in ra.
10. Các model cloud hiện có không bị ảnh hưởng.
11. `stop-agent02.bat` chỉ tắt PID đang theo dõi.
12. `node scripts/check-docs-parity.mjs` pass.

## Mốc nguồn tham chiếu

Tài liệu OpenClaw:

- Source setup: https://docs.openclaw.ai/start/setup
- Gateway CLI: https://docs.openclaw.ai/cli/gateway
- Control UI: https://docs.openclaw.ai/web/control-ui
- vLLM provider: https://docs.openclaw.ai/providers/vllm
- Mốc source: `src/commands/self-hosted-provider-setup.ts`
- Mốc source: `extensions/vllm/index.ts`
- Mốc source: `src/commands/dashboard.ts`

Tài liệu llama.cpp:

- Server guide: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
- Build guide: https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md
- REST API changelog: https://github.com/ggml-org/llama.cpp/issues/9291

Chi tiết llama-server chính (từ skill `llama-knowledge`):

- `--api-key` bật bearer auth cho tất cả endpoint trừ `/health`
- `/health` luôn public
- `/v1/models` cần `Authorization: Bearer <key>` khi `--api-key` được đặt
- Port cố định `8420` là quy ước của Agent-02, không phải mặc định của llama.cpp
