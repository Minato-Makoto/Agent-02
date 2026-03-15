---
title: Blueprint Windows cho Agent-02 với OpenClaw và llama.cpp
description: Blueprint chỉ dành cho Windows để chạy Agent-02 bằng flow chính thức của OpenClaw và `llama.cpp` như một provider OpenAI-compatible bên ngoài.
---

# Blueprint Windows cho Agent-02 với OpenClaw và llama.cpp

## Mục tiêu

Blueprint này dựng lại Agent-02 trên Windows native với một ranh giới rõ ràng:

- OpenClaw tiếp tục là control plane duy nhất cho gateway, dashboard, session, channel, node và tools.
- `llama-server.exe` của `llama.cpp` chỉ là model server OpenAI-compatible chạy bên ngoài.
- Việc nối provider phải đi qua flow setup có sẵn của OpenClaw với base URL, API key và model id tường minh.
- Không được có custom launcher tự chọn model, tự inject provider state, hoặc tự ghi config OpenClaw thay cho user.

## Install path được chọn

Agent-02 phải đi theo flow cài đặt OpenClaw chính thức trên Windows PowerShell:

1. cài OpenClaw bằng `install.ps1`
2. chạy `openclaw onboard --flow manual --install-daemon`
3. chạy `llama-server.exe` như một process Windows riêng
4. nối OpenClaw với `llama-server.exe` qua chính flow provider của OpenClaw

Cách này giữ toàn bộ hành vi service khởi động, gateway auth, dashboard, provider setup, và các phần mở rộng sau này của OpenClaw ở trong upstream OpenClaw thay vì dồn vào script nội bộ của repo.

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
- expose `/v1/models`
- phục vụ `/v1/chat/completions`
- enforce API key dùng cho local provider

### Repo không được sở hữu

- API key provider mặc định
- model id mặc định
- catalog provider ẩn
- các lần ghi tự động vào `%USERPROFILE%\\.openclaw\\openclaw.json`
- các lần ghi tự động vào `models.json` ở agent local

## Layout mục tiêu trên Windows

Dùng user profile Windows bình thường và giữ state của OpenClaw ở home mặc định, trừ khi sau này cần tách riêng.

- Config OpenClaw: `%USERPROFILE%\\.openclaw\\openclaw.json`
- Workspace OpenClaw: `%USERPROFILE%\\.openclaw\\workspace\\`
- Credentials và runtime state của OpenClaw: `%USERPROFILE%\\.openclaw\\`
- Model local: `D:\\Models\\`
- Source checkout tùy chọn cho `llama.cpp`: `D:\\src\\llama.cpp\\`

Bản cài chuẩn không cần runtime state nằm trong repo.

## Bước 1: Cài OpenClaw trên Windows

Mở PowerShell bình thường và chạy installer chính thức:

```powershell
iwr -useb https://openclaw.ai/install.ps1 | iex
openclaw doctor
```

Kết quả mong đợi:

- CLI của OpenClaw có trên `PATH`
- Node.js có sẵn nếu installer phải bootstrap nó
- `openclaw doctor` báo bản cài local dùng được

## Bước 2: Tạo gateway local cho Agent-02

Chạy onboarding ở manual mode để gateway auth và hành vi startup luôn tường minh:

```powershell
openclaw onboard --flow manual --install-daemon
```

Trong lúc onboarding, giữ các quyết định sau ở dạng Windows-local:

- gateway mode: local
- bind address: chỉ loopback
- auth: bật token
- daemon install: bật
- workspace: giữ workspace mặc định của OpenClaw, trừ khi bạn có Windows profile riêng cho Agent-02

Nếu wizard hỏi phần model setup trước khi `llama-server.exe` sẵn sàng, hãy bỏ qua phần đó trước rồi quay lại sau Bước 5.

Sau khi onboarding xong, kiểm tra service trước:

```powershell
openclaw gateway status
openclaw dashboard
```

`openclaw dashboard` phải in ra hoặc mở đúng URL Control UI local của gateway vừa tạo.

## Bước 3: Cài llama.cpp trên Windows

### Cách khuyến nghị: dùng package Windows dựng sẵn

Dùng package Windows chính thức trước:

```powershell
winget install llama.cpp
Get-Command llama-server
```

### Cách tùy chọn: build từ source trên Windows

Chỉ dùng cách này nếu bạn cần backend cụ thể hoặc muốn pin một source checkout:

```powershell
git clone https://github.com/ggml-org/llama.cpp.git D:\src\llama.cpp
cd D:\src\llama.cpp
cmake -B build
cmake --build build --config Release
```

Nếu build cho GPU, thêm đúng backend Windows bạn dùng, ví dụ `-DGGML_CUDA=ON` hoặc `-DGGML_VULKAN=ON`, trước bước build.

## Bước 4: Chuẩn bị model local

Đặt GGUF mà Agent-02 sẽ dùng vào một path Windows bình thường, ví dụ:

```powershell
New-Item -ItemType Directory -Force D:\Models | Out-Null
```

Quy tắc chọn model:

- dùng GGUF dạng instruct hoặc chat, không dùng base model thô
- ưu tiên model đã có sẵn chat template đúng
- nếu model cần template tường minh, truyền đúng flag template của llama.cpp khi khởi động server

## Bước 5: Chạy `llama-server.exe`

Giữ model server ở local và có auth. Ví dụ:

```powershell
$env:LLAMA_SERVER_API_KEY = "agent02-local"
$ModelPath = "D:\Models\qwen2.5-coder-7b-instruct-q4_k_m.gguf"

llama-server.exe `
  -m $ModelPath `
  --host 127.0.0.1 `
  --port 8080 `
  --api-key $env:LLAMA_SERVER_API_KEY
```

Xác minh surface của provider trước khi chạm vào model settings của OpenClaw:

```powershell
$headers = @{ Authorization = "Bearer $env:LLAMA_SERVER_API_KEY" }
Invoke-RestMethod -Headers $headers -Uri "http://127.0.0.1:8080/v1/models"
```

Phải dùng đúng model id trả về ở bước tiếp theo.

## Bước 6: Đăng ký `llama-server.exe` vào OpenClaw

Không hand-edit config của OpenClaw trừ khi đang khôi phục một bản cài hỏng. Hãy dùng flow setup có sẵn của OpenClaw.

Các lựa chọn nên dùng:

- chạy lại `openclaw onboard` nếu trước đó bạn cố ý bỏ qua phần model setup
- hoặc chạy `openclaw configure` và hoàn tất phần model hoặc provider ở đó
- hoặc mở màn hình config trong Control UI từ dashboard và dùng flow provider có sẵn

Các giá trị phải luôn tường minh:

- loại provider: self-hosted OpenAI-compatible hoặc flow explicit provider kiểu vLLM
- base URL: `http://127.0.0.1:8080/v1`
- API key: đúng giá trị đang dùng ở `llama-server.exe --api-key`
- model id: đúng id mà `GET /v1/models` trả về

Sau khi provider xuất hiện, xác nhận model nhìn thấy được từ phía OpenClaw:

```powershell
openclaw models list
```

Nếu muốn Agent-02 ưu tiên model này mặc định, hãy đặt đúng cặp provider và model id mà OpenClaw expose:

```powershell
openclaw models set <provider>/<model-id>
```

Thay `<provider>/<model-id>` bằng đúng giá trị đang hiện ra trong `openclaw models list`.

## Bước 7: Chỉ dùng OpenClaw làm front door

Sau khi setup provider xong, mọi tính năng của OpenClaw phải đi qua OpenClaw, không đi thẳng vào `llama-server.exe`.

### Control UI

- mở bằng `openclaw dashboard`
- đăng nhập bằng gateway token nếu được hỏi
- xác nhận chat stream câu trả lời qua local provider

### Channels

- đăng nhập channel được hỗ trợ bằng `openclaw channels login`
- giữ toàn bộ channel credentials trong state của OpenClaw, không để trong script khởi động llama.cpp

### Nodes và devices

- xem trạng thái device bằng `openclaw devices list`
- approve device chờ bằng `openclaw devices approve <id>`
- xem kết nối node bằng `openclaw nodes status`

### Web tools và plugins

- cấu hình web search hoặc browser tooling bằng `openclaw configure --section web`
- chỉ bật OpenProse qua plugin của OpenClaw: `openclaw plugins enable open-prose`
- restart gateway nếu OpenClaw yêu cầu sau khi đổi plugin

## Kỳ vọng đầy đủ tính năng

Việc dùng `llama-server.exe` làm local model backend không được biến OpenClaw thành một vỏ chat mỏng.

Kỳ vọng được hỗ trợ cho Agent-02 là:

- suy luận model local đến từ llama.cpp
- gateway auth và dashboard vẫn ở OpenClaw
- session, routing và tools vẫn ở OpenClaw
- channel integrations vẫn ở OpenClaw
- nodes, approval và trust của device vẫn ở OpenClaw
- model selection vẫn ở OpenClaw sau khi provider đã được đăng ký

## Drift bị cấm

Không được đưa lại bất kỳ điều nào sau đây:

- launcher nội bộ repo tự inject `VLLM_API_KEY` hoặc provider state tương đương sau lưng OpenClaw
- `MODEL_PATH`, `DEFAULT_MODEL_ID`, hoặc `MODELS_DIR` như policy layer để chọn model cho OpenClaw
- script trong repo tự ghi config vào OpenClaw
- channel, node, hoặc dashboard đi trực tiếp tới `llama-server.exe`
- nhét gateway token vào lệnh startup của llama.cpp
- bind bất kỳ service nào ra public interface trước khi auth được cấu hình có chủ đích

## Checklist xác minh

Chạy checklist này theo đúng thứ tự:

1. `openclaw doctor` pass.
2. `openclaw gateway status` cho thấy local gateway đã được cài và truy cập được.
3. `openclaw dashboard` mở đúng URL Control UI local.
4. `Invoke-RestMethod http://127.0.0.1:8080/v1/models` chạy được với API key của llama.cpp.
5. `openclaw models list` thấy model local provider đã cấu hình.
6. `openclaw models set ...` chạy được với model Agent-02 mong muốn.
7. Một cuộc chat thật trong Control UI stream được phản hồi từ local model.
8. Nếu cần channels, `openclaw channels login` chạy được và traffic của channel vẫn đi qua OpenClaw.
9. Nếu cần nodes hoặc devices, `openclaw devices list` và `openclaw nodes status` cho ra trạng thái khỏe.
10. Nếu cần web tools hoặc OpenProse, hãy bật bằng `openclaw configure` hoặc `openclaw plugins`, rồi xác minh lại từ dashboard.

## Mốc nguồn tham chiếu

Tài liệu OpenClaw:

- Getting started: https://docs.openclaw.ai/start/getting-started
- Source setup: https://docs.openclaw.ai/start/setup
- Gateway CLI: https://docs.openclaw.ai/cli/gateway
- Onboarding CLI: https://docs.openclaw.ai/cli/onboard
- Configure CLI: https://docs.openclaw.ai/cli/configure
- Control UI: https://docs.openclaw.ai/web/control-ui
- vLLM provider: https://docs.openclaw.ai/providers/vllm
- Mốc source: `src/commands/self-hosted-provider-setup.ts`
- Mốc source: `extensions/vllm/index.ts`
- Mốc source: `src/commands/dashboard.ts`

Tài liệu llama.cpp:

- Cài trên Windows: https://github.com/ggml-org/llama.cpp/blob/master/docs/install.md
- Build trên Windows: https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md
- Server API: https://github.com/ggml-org/llama.cpp/blob/master/examples/server/README.md
