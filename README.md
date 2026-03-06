# Agent-02 v4.20

Private AI gateway for people who want their own assistant without editing code.

Agent-02 gives you one control panel to:

- chat with a local or cloud AI model
- keep history on your own machine
- approve sensitive actions before they run
- connect Telegram or Discord later if you want

[Đọc bằng tiếng Việt](README_vi.md)

## Start Here

1. Install [Node.js 22 or newer](https://nodejs.org/).
2. Open this folder.
3. Double-click [`agent02.bat`](agent02.bat) on Windows.
4. Wait for the browser to open `http://localhost:8420`.

That is enough for the first run.

## Local AI Setup

Agent-02 v4.20 automatically looks for:

- `D:\AI Agent\llama.cpp`
- `D:\AI Agent\models`

If your `.gguf` models are inside `D:\AI Agent\models`, the Settings screen will list them automatically.

## Cloud AI Setup

If you prefer OpenAI, Anthropic, DeepSeek, Gemini, Groq, or OpenRouter:

1. Open **Settings**
2. Choose the provider
3. Paste your API key
4. Save settings

## What The Control Panel Does

- **Dashboard**: shows runtime health and recent events
- **Chat**: talk to Agent-02 directly in the browser
- **Sessions**: reopen older conversations
- **Approvals**: allow or deny sensitive actions
- **Logs**: view system history
- **Settings**: change provider, model, workspace, and safety options

## Safety

Agent-02 was upgraded in v4.20 with:

- config migration for older installs
- stricter workspace path protection
- safer web fetching that blocks local/private targets
- shell execution locked to the workspace and still approval-based
- UI and API contracts aligned so sessions, approvals, and settings behave correctly

## Your Data

Your local files live in `data/`.

- `data/config.json`: saved settings and encrypted secrets
- `data/agent02.db`: chat history and logs
- `data/instructions/system.md`: Agent personality/instructions
- `data/workspace/`: safe working folder for file and shell tools

## Non-Technical Guide

If you want a step-by-step guide without developer language, read:

- [Quick Start (English)](docs/QUICKSTART_en.md)
- [Quick Start (Vietnamese)](docs/QUICKSTART_vi.md)
