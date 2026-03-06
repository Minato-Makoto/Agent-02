# Quick Start For Non-Technical Users

## What is Agent-02?

Agent-02 is a control panel for running your own AI assistant on your own machine.

You can:

- use local `.gguf` models
- or use cloud providers with API keys
- approve sensitive actions before anything risky runs

## What do you need?

- A Windows PC with Node.js 22+
- For local AI:
  - `llama-server.exe` inside `D:\AI Agent\llama.cpp`
  - `.gguf` models inside `D:\AI Agent\models`
- For cloud AI:
  - an API key from your provider

## How to open Agent-02

1. Open the `agent-02` folder
2. Double-click `agent02.bat`
3. Wait for the browser to open `http://localhost:8420`

On the first run, it installs packages and builds automatically.

## How to use a local model

1. Open **Settings**
2. Set **Provider** to `llama.cpp (Local GGUF)`
3. Choose a model from **Detected local GGUF models**
4. Click **Save Settings**
5. Go back to **Chat**

## How to use a cloud model

1. Open **Settings**
2. Choose a provider such as OpenAI or Anthropic
3. Enter the model name
4. Paste your API key
5. Click **Save Settings**

## If Agent-02 asks for approval

Sensitive actions are never run automatically.

You will see:

- a popup
- or the **Approvals** tab

Choose:

- **Approve** to allow it
- **Deny** to block it

## Common problems

### 1. My local model is missing

Check that:

- the file ends in `.gguf`
- the file is inside `D:\AI Agent\models`

### 2. Chat opens but nothing answers

Check in **Settings**:

- you selected a provider
- you selected a model or entered an API key

### 3. Telegram or Discord still does not connect

Some connector changes need an app restart after saving settings.

## Important files

- `data/config.json`: saved settings
- `data/instructions/system.md`: Agent behavior/instructions
- `data/workspace/`: safe working folder for AI tools
