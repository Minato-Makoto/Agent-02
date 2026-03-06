# Agent-02 v4.20

Trợ lý AI cá nhân chạy trên máy của bạn, dành cho người không rành kỹ thuật.

Agent-02 giúp bạn:

- chat với AI local hoặc AI cloud trong một màn hình duy nhất
- giữ lịch sử và cài đặt trên máy của bạn
- duyệt thủ công mọi hành động nhạy cảm trước khi chạy
- mở rộng sang Telegram hoặc Discord khi cần

[Read in English](README.md)

## Bắt Đầu Nhanh

1. Cài [Node.js 22 trở lên](https://nodejs.org/).
2. Mở thư mục dự án này.
3. Double-click vào [`agent02.bat`](agent02.bat).
4. Chờ trình duyệt mở `http://localhost:8420`.

Lần đầu chỉ cần vậy.

## Nếu Muốn Chạy AI Local

Agent-02 v4.20 tự dò sẵn hai nơi này:

- `D:\AI Agent\llama.cpp`
- `D:\AI Agent\models`

Nếu file model `.gguf` của bạn nằm trong `D:\AI Agent\models`, màn hình **Settings** sẽ tự hiện danh sách model để chọn.

## Nếu Muốn Dùng AI Cloud

Bạn có thể dùng OpenAI, Anthropic, DeepSeek, Gemini, Groq hoặc OpenRouter:

1. Mở **Settings**
2. Chọn nhà cung cấp
3. Dán API key
4. Bấm **Save Settings**

## Các Tab Trong Giao Diện

- **Dashboard**: xem trạng thái hệ thống
- **Chat**: nói chuyện trực tiếp với Agent-02
- **Sessions**: mở lại hội thoại cũ
- **Approvals**: duyệt hoặc từ chối hành động nhạy cảm
- **Logs**: xem lịch sử hoạt động
- **Settings**: đổi model, nơi làm việc, và các tuỳ chọn an toàn

## Bản 4.20 Đã Nâng Cấp Gì

- tự hiểu và migrate config cũ sang cấu trúc mới
- sửa lệch contract giữa UI và backend
- hiển thị session đúng tên người dùng, thời gian, số tin nhắn
- phát hiện local GGUF models ngay trong giao diện
- system prompt có thể sửa trực tiếp trong Settings
- sandbox path chặt hơn
- web fetch an toàn hơn, chặn truy cập local/private network
- shell command bị khóa trong workspace và vẫn phải duyệt tay

## Dữ Liệu Của Bạn Nằm Ở Đâu

Mọi dữ liệu local nằm trong `data/`:

- `data/config.json`: cấu hình và secret đã mã hóa
- `data/agent02.db`: lịch sử chat và log
- `data/instructions/system.md`: tính cách / luật của Agent
- `data/workspace/`: vùng làm việc an toàn cho file và shell tools

## Tài Liệu Dành Cho Người Không Biết Code

Xem hướng dẫn từng bước tại:

- [Quick Start (VI)](docs/QUICKSTART_vi.md)
- [Quick Start (EN)](docs/QUICKSTART_en.md)
