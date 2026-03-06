# Hướng Dẫn Nhanh Cho Người Không Biết Code

## Agent-02 là gì?

Đây là một màn hình điều khiển để bạn dùng AI ngay trên máy của mình.

Bạn có thể:

- dùng model local `.gguf`
- hoặc dùng AI cloud bằng API key
- duyệt thủ công các lệnh nhạy cảm trước khi AI được phép chạy

## Cần chuẩn bị gì?

- Một máy Windows đã cài Node.js 22+
- Nếu chạy local:
  - `llama-server.exe` trong `D:\AI Agent\llama.cpp`
  - model `.gguf` trong `D:\AI Agent\models`
- Nếu chạy cloud:
  - API key của nhà cung cấp bạn chọn

## Cách mở Agent-02

1. Mở thư mục `agent-02`
2. Double-click `agent02.bat`
3. Chờ trình duyệt mở trang `http://localhost:8420`

Nếu là lần đầu, chương trình sẽ tự cài thư viện và build.

## Cách chọn model local

1. Mở tab **Settings**
2. Ở ô **Provider**, chọn `llama.cpp (Local GGUF)`
3. Ở ô **Detected local GGUF models**, chọn model bạn muốn
4. Bấm **Save Settings**
5. Quay lại tab **Chat** và bắt đầu nhắn

## Cách dùng API key cloud

1. Mở tab **Settings**
2. Chọn nhà cung cấp như OpenAI hoặc Anthropic
3. Điền model name
4. Dán API key vào ô tương ứng
5. Bấm **Save Settings**

## Nếu AI xin quyền chạy lệnh

Agent-02 sẽ không tự chạy lệnh nhạy cảm.

Bạn sẽ thấy:

- popup trên màn hình
- hoặc tab **Approvals**

Bạn chỉ cần bấm:

- **Approve** nếu đồng ý
- **Deny** nếu không đồng ý

## Các lỗi hay gặp

### 1. Không thấy model local

Kiểm tra lại:

- file model có đuôi `.gguf`
- model nằm trong `D:\AI Agent\models`

### 2. Mở app nhưng chat không trả lời

Kiểm tra trong **Settings**:

- đã chọn provider chưa
- đã chọn model hoặc dán API key chưa

### 3. Telegram hoặc Discord chưa hoạt động sau khi lưu

Một số thay đổi connector cần khởi động lại app sau khi save.

## Các file quan trọng

- `data/config.json`: nơi lưu cấu hình
- `data/instructions/system.md`: nơi đổi tính cách AI
- `data/workspace/`: vùng làm việc an toàn của AI
