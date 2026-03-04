# ⚡ Agent-02 — Self-Hosted AI Gateway

**One click. Your AI. Your rules. 100% private & secure.**

Welcome to **Agent-02**! A secure, self-hosted gateway connecting state-of-the-art AI models (cloud or local) to your messaging platforms like WhatsApp, Telegram, and Discord—all running completely on your own machine.

[Read this in Vietnamese / Đọc bằng tiếng Việt](README_vi.md)

---

## 🌟 Features

- **100% Privacy:** Your chat history, API keys, and settings live locally in the `data/` folder.
- **Human-in-the-Loop Consent:** The AI cannot execute dangerous operations (like Shell commands) without your explicit approval via the Control UI.
- **Easy Deployment:** Includes a single Windows `.bat` script for non-devs, and a `docker-compose.yml` for server hosting.
- **Dynamic Personality:** Adjust the AI's behavior via a simple `system.md` file without touching code.
- **Broad Model Support (2026):** Connects to OpenAI, Anthropic, Gemini, DeepSeek, or run 100% offline using Ollama and Llama.cpp.

---

## 📋 Prerequisites

Depending on how you want to run Agent-02, you will need:
- **For Windows (Easy Mode):** [Node.js](https://nodejs.org/) (Version 22+) installed on your computer.
- **For Servers (Docker Mode):** Docker and Docker Compose installed.

---

## 🚀 Installation

### Windows Easy Installation
1. Download or clone this repository to your machine.
2. Open the `agent-02` folder.
3. Double-click the `agent02.bat` file.
   - *On the first run, it will automatically install dependencies and start the server.*

### Linux / Server Installation (Docker)
```bash
git clone https://github.com/yourname/agent-02.git
cd agent-02
docker-compose up -d
```

---

## 💻 Usage

Once the server is running, open your web browser and go to:
👉 **http://localhost:8080**

This will open the **Control UI** where you can manage your AI.

### 1. Connecting Platforms
You can chat directly in the UI, or link it to messaging apps via the "Connectors" tab:
- **Telegram:** Talk to [@BotFather](https://t.me/botfather) to create a bot and get a Token.
- **Discord:** Create a bot at the [Discord Developer Portal](https://discord.com/developers).
- **WhatsApp:** Set up an official app on [Meta for Developers](https://developers.facebook.com) for the WhatsApp Cloud API.

### 2. Choosing an AI Model
In the **Settings** tab, choose your AI brain:
- **Cloud AI:** Select provider (OpenAI, Anthropic, etc.) and paste your API Key.
- **Offline AI:** Connect your local Ollama or point to a `.gguf` file using Llama.cpp for complete offline privacy.

### 3. Setting AI Personality (System Prompt)
Want the AI to act differently?
1. Open `data/instructions/system.md` in any text editor.
2. Write your custom behavior instructions.
3. Save the file. The AI adopts the new personality immediately on the next chat session.

### 4. Sandboxed Skills
Agent-02 includes tools the AI can use:
- **Web Search:** Search the web privately via DuckDuckGo.
- **File System:** Read/write files, rigidly restricted to the allowed workspace.
- **Shell Commands:** Try to run computer commands—**always pauses and asks you to explicitly "Approve" or "Deny"**.

---

## 🏗️ Project Structure

The codebase is structured in modern TypeScript running on Node.js:

```
agent-02/
├── src/                    # Backend Source Code (TypeScript)
│   ├── index.ts            # Entry CLI
│   ├── api/                # Fastify REST & WebSocket servers
│   ├── gateway/            # Event bus, router, session handling
│   ├── adapters/           # Connectors (Telegram, Discord, WhatsApp)
│   ├── llm/                # API wrappers for AI Providers
│   └── skills/             # Sandboxed AI Tools
├── ui/                     # Control UI
│   └── dist/               # Compiled HTML/JS/CSS Interface
├── data/                   # Your Local Data (Created on first run)
│   ├── config.json         # AES-256 Encrypted API Keys
│   ├── agent02.sqlite      # Chat history database
│   └── instructions/       # system.md rules
├── docker-compose.yml      # Deployment config
├── install.sh              # Bash installer
├── agent02.bat             # Windows runner
├── package.json            # Node dependencies
└── tsconfig.json           # TypeScript config
```

---

## 🛡️ Data Storage & Privacy

All sensitive user data is stored safely within the `data/` directory. 
- API Keys inside `config.json` are encrypted at rest using AES-256-GCM.
- **To Backup/Migrate:** Simply copy your `data/` folder to your new machine or server.

---

## 🤝 Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## 📝 License
[MIT](https://choosealicense.com/licenses/mit/)
