# Agent-02

Agent-02 là trạm AI local chỉ dành cho Windows, được xây trên OpenClaw core và `llama-server` chạy local.

Runtime contract hiện tại được giữ nguyên:

- `run.bat` là launcher chính.
- `stop.bat` là file tắt ứng dụng chính.
- `run.local.bat` là lớp override local.
- `.openclaw/` chứa config, log, workspace và runtime state.
- `llama-server` lắng nghe trên `127.0.0.1:8000`.
- OpenClaw gateway và dashboard lắng nghe trên `127.0.0.1:18789`.

Fork này có chủ đích bỏ toàn bộ surface mobile, macOS, Docker và release-distribution để repo tập trung vào workflow local trên Windows.

## Tài Liệu

- Tài liệu English: [docs/en/overview.md](docs/en/overview.md)
- Tài liệu tiếng Việt: [docs/vi/overview.md](docs/vi/overview.md)

## Khởi Động Nhanh

1. Cài Node.js 22+ và đảm bảo `node` cùng `corepack` có trong `PATH`.
2. Đặt `llama-server.exe` vào `..\\llama.cpp\\`.
3. Đặt các file model `.gguf` vào `..\\models\\`.
4. Nếu cần, chỉnh [run.local.bat](run.local.bat) để override model, GPU layers, port hoặc đường dẫn.
5. Double-click [run.bat](run.bat) để khởi động stack.
6. Double-click [stop.bat](stop.bat) khi muốn tắt hoàn toàn.

Lần chạy đầu tiên, launcher sẽ tự cài dependencies và build project nếu `dist/entry.js` chưa tồn tại.

## Chọn Model

Agent-02 không hardcode context window hay output token limit trong launcher.

- Nếu `DEFAULT_MODEL_ID` được set trong [run.local.bat](run.local.bat), model đó sẽ là default của Agent-02.
- Nếu `DEFAULT_MODEL_ID` để trống, launcher sẽ đọc `GET /v1/models` từ `llama-server` và lấy model ID đầu tiên theo thứ tự alphabet ổn định.
- Sau đó OpenClaw dùng `vllm/<model-id>` làm primary model mặc định.

## Vận Hành

- Dashboard: `http://127.0.0.1:18789/`
- API của `llama-server`: `http://127.0.0.1:8000/v1`
- Web UI của `llama.cpp` khi cần debug: `http://127.0.0.1:8000/`
- Log: `.openclaw/logs/`

Để tắt hoàn toàn ứng dụng, ưu tiên dùng [stop.bat](stop.bat).

PowerShell fallback thủ công:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8000,18789 -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique |
  ForEach-Object { Stop-Process -Id $_ -Force }
```

## Phạm Vi Repo

Repo này giữ:

- TypeScript core và UI của OpenClaw
- launcher flow hiện tại trên Windows
- local model integration thông qua `llama-server`
- Canvas/A2UI build path đang thực sự cần cho build hiện tại

Repo này bỏ:

- native app surface của Android, iOS và macOS
- Docker và các flow container packaging
- release automation và maintainer packaging baggage
- locale docs ngoài English và Vietnamese
