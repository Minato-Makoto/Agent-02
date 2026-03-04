# ⚡ Agent-02 — Cổng Trợ Lý AI Cá Nhân

**Chỉ cần một click. AI của bạn. Luật của bạn. Riêng tư & Bảo mật 100%.**

Chào mừng đến với **Agent-02**! Một hệ thống cổng nối (gateway) tự lưu trữ, giúp kết nối các mô hình AI tiên tiến nhất hiện nay (Đám mây hoặc Chạy nội bộ) tới các ứng dụng nhắn tin quen thuộc như WhatsApp, Telegram, Discord—tất cả đều hoạt động an toàn ngay trên máy tính của bạn.

[Read this in English](README.md)

---

## 🌟 Các Tính Năng Nổi Bật

- **Riêng tư 100%:** Lịch sử chat, các API Key bí mật, và cài đặt của bạn đều nằm an toàn trên ổ cứng trong thư mục `data/`.
- **Cơ chế Kiểm duyệt (Human-in-the-Loop):** AI cực kỳ an toàn, không thể tự gõ lệnh hệ thống nguy hiểm nếu không có thao tác bấm "Chấp thuận" (Approve) từ chính tay bạn trên giao diện quản lý.
- **Dễ triển khai:** Cung cấp sẵn file click-đúp `.bat` cho môi trường Windows, và file `docker-compose.yml` tiêu chuẩn cho những ai muốn treo máy chủ (Server VPS).
- **Tính cách linh hoạt:** Bạn có thể quy định cách con AI hành xử thoải mái qua file văn bản `system.md` mà không cần biết viết mã code.
- **Hỗ trợ đa dạng Model (2026):** Hỗ trợ cắm API của OpenAI, Anthropic, Gemini, DeepSeek, hoặc chạy 100% không cần Internet với Ollama và Llama.cpp.

---

## 📋 Yều Cầu Hệ Thống

Tùy vào cách bạn muốn chạy Agent-02, bạn sẽ cần cài đặt:
- **Dành cho Windows (Dễ nhất):** Được cài đặt sẵn [Node.js](https://nodejs.org/) (Phiên bản 22 trở lên).
- **Dành cho Máy chủ / VPS (Docker):** Máy đã cài đặt Docker và Docker Compose.

---

## 🚀 Hướng Dẫn Cài Đặt

### Cài đặt nhanh trên Windows
1. Tải về hoặc Clone dự án này về máy tính.
2. Mở thư mục `agent-02`.
3. Click đúp vào file `agent02.bat`.
   - *Trong lần chạy đầu tiên, mã lệnh sẽ tự động cài các thư viện cần thiết và bật Server lên.*

### Cài đặt trên Máy chủ Linux (Sử dụng Docker)
```bash
git clone https://github.com/yourname/agent-02.git
cd agent-02
docker-compose up -d
```

---

## 💻 Cách Sử Dụng

Khi Server báo đang chạy, hãy mở trình duyệt web lên và truy cập:
👉 **http://localhost:8080**

Màn hình **Bảng Điều Khiển (Control UI)** sẽ hiện ra, đây là nơi bạn quản lý toàn bộ hệ thống AI của mình.

### 1. Kết nối với Ứng dụng Nhắn tin
Bạn có thể chat trực tiếp trên Giao diện web, hoặc gắn AI vào nền tảng chat ở tab "Connectors":
- **Telegram:** Nhắn tin với [@BotFather](https://t.me/botfather) trên Telegram, tạo bot mới và lấy mã Token dán vào.
- **Discord:** Tạo bot truy cập tại [Discord Developer Portal](https://discord.com/developers).
- **WhatsApp:** Tạo Official App miễn phí tại [Meta for Developers](https://developers.facebook.com) (WhatsApp Cloud API).

### 2. Chọn Não cho AI (AI Model)
Mở tab **Settings**, bạn được quyền quyết định AI dùng model nào:
- **AI Đám mây (Cloud):** Chọn nhà cung cấp (OpenAI, Anthropic, v.v...) và dán API Key vào.
- **AI Ngoại tuyến (Offline):** Liên kết với máy chủ local Ollama của bạn hoặc trỏ đường dẫn tới một file `.gguf` để chạy AI siêu việt hoàn toàn ngắt mạng.

### 3. Đổi Tính Cách AI (System Prompt)
Bạn muốn AI phục vụ theo ý mình?
1. Mở file `data/instructions/system.md` lên bằng Notepad.
2. Gõ luật lệ bảo AI cách nó nên trả lời.
3. Lưu file lại. Tính cách mới sẽ được áp dụng ngay lập tức ở khung chat tiếp theo.

### 4. Kỹ Năng (Sandboxed Skills)
Agent-02 có nhiều kỹ năng phụ trợ bạn có thể cấu hình:
- **Web Search:** AI tự ẩn danh duyệt web tìm thông tin bằng DuckDuckGo.
- **File System:** AI đọc/ghi file nhưng bị giam lỏng nghiêm ngặt, chỉ hoạt động trong thư mục chỉ định sẵn.
- **Shell Commands:** AI gõ phím thao tác hệ thống máy tính—**Nó luôn bị tạm thời đóng băng mọi hoạt động và hiện Pop-up chờ bạn ấn "Đồng Ý" hoặc "Từ chối" trên trang quản lý**.

---

## 🏗️ Cấu Trúc Dự Án

Source Code được xây dựng bằng kiến trúc chuẩn TypeScript chạy trên Node.js như sau:

```
agent-02/
├── src/                    # Source Code Lõi (TypeScript)
│   ├── index.ts            # Điểm khởi chạy CLI
│   ├── api/                # Máy chủ API REST & WebSockets
│   ├── gateway/            # Quản lý sự kiện, điều phối luồng và phiên Chat
│   ├── adapters/           # Các cổng kết nối tin nhắn (Telegram, Discord...)
│   ├── llm/                # Trình phân giải và kết nối Model AI
│   └── skills/             # Các Kỹ năng (Đóng hộp Sandbox)
├── ui/                     # Bảng Điều Khiển
│   └── dist/               # Folder chứa Giao diện HTML/JS/CSS siêu nhẹ
├── data/                   # Dữ liệu Nội bộ của Bạn (Tự sinh ra lúc chạy)
│   ├── config.json         # API Keys đã mã hóa AES-256
│   ├── agent02.sqlite      # Cơ sở dữ liệu ghi nhớ lịch sử chat
│   └── instructions/       # Tính cách hệ thống system.md
├── docker-compose.yml      # Tùy chỉnh lúc Deploy
├── install.sh              # Script cài đặt cho Linux
├── agent02.bat             # File thực thi cho Windows
├── package.json            # Các thư viện phụ thuộc của Node.js
└── tsconfig.json           # Cấu hình biên dịch TypeScript
```

---

## 🛡️ Dữ liệu và An ninh

Tất cả thông tin nhạy cảm của bạn chỉ tạo và nằm gọn bên trong thư mục `data/`.
- Mã API Key nằm ở `config.json` mặc định sẽ bị phần mềm băm nhỏ (Mã hóa AES-256-GCM ở trạng thái nghỉ). Bạn nhập vào xong không thể dò lại chữ gốc, đảm bảo an toàn nếu máy bị hack.
- **Chuyển máy tính:** Rất đơn giản, hãy copy toàn bộ thư mục `data/` này từ máy này qua máy khác, hoặc bê lên Server VPS là hệ thống của bạn y nguyên. Không lo làm lại từ đầu.

---

## 🤝 Đóng Góp Nâng Cấp
Chúng tôi hoàn toàn hoan nghênh (Pull requests). Nếu bạn muốn thực hiện các thay đổi lớn, vui lòng mở "Issue" trước để cùng thảo luận.

## 📝 Bản Quyền
[MIT](https://choosealicense.com/licenses/mit/)
