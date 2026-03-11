# Agent-02 Tutorial (EN)

This tutorial covers the supported Agent-02 flow: Gateway, WebUI, and channel operations.

## 1. Recommended Layout

```text
D:\AI Agent\
|- Agent-02\
|- llama.cpp\llama-server.exe
`- models\
   |- model-a.gguf
   `- model-b.gguf
```

Default launcher values:

- `SERVER_EXE=..\llama.cpp\llama-server.exe`
- `MODELS_DIR=..\models`
- `GATEWAY_HOST=127.0.0.1`
- `GATEWAY_PORT=18789`
- `HOST=127.0.0.1`
- `PORT=8080`
- `REASONING_EFFORT=` (blank by default)
- `MAX_REQUESTS_PER_MINUTE=0` (disabled by default)

Put machine-specific overrides in `run.local.bat`.

## 2. First Launch

1. Install Python 3.10+.
2. Ensure `llama-server.exe` is present.
3. Put one or more GGUF models in `..\models`.
4. Run `run.bat`.

On first launch the script may install Python packages and the Playwright Chromium runtime.

## 3. Runtime Behavior

`run.bat` does four things:

1. starts `llama-server` in router mode
2. starts Agent-02 Gateway
3. waits for `/health`
4. opens `http://127.0.0.1:18789/webchat` unless `AUTO_OPEN_BROWSER=0`

If Agent-02 is already running on the target gateway port, the launcher reuses that instance and opens the existing WebUI instead of starting a duplicate server.

Useful URLs:

- Gateway health: `http://127.0.0.1:18789/health`
- WebUI: `http://127.0.0.1:18789/webchat`
- llama.cpp Web UI: `http://127.0.0.1:8080/`

## 4. WebUI Basics

The WebUI has three main areas:

- left rail: sessions and inbox
- center: chat canvas
- right dock: `Models`, `Channels`, `Pairing`, `Settings`

The default logical session is `agent:main:main`.

If the router reports a single model, Agent-02 auto-selects it. If the router reports multiple models, the current session is blocked until you choose one in WebUI.

## 5. Channel Setup

Channels supported in this wave:

- Telegram
- Discord
- Zalo

Channel config is stored in `workspace/gateway/config.json`.

You can configure channels from WebUI or by setting environment fallbacks:

- `TELEGRAM_BOT_TOKEN`
- `DISCORD_BOT_TOKEN`
- `ZALO_BOT_TOKEN`

WebUI never echoes secrets back after they are saved.

## 6. Pairing and Access Control

DM default policy is `pairing`.

That means:

1. the first DM from a sender is blocked
2. Agent-02 returns a pairing code
3. you approve or reject that code in WebUI > `Pairing`

Group and guild traffic is fail-closed by default:

- `groupPolicy=allowlist`
- `requireMention=true`

## 7. Session Routing

Routing keys used in this wave:

- WebChat and approved DMs: `agent:main:main`
- Telegram and Zalo groups: `agent:main:<channel>:group:<id>`
- Discord guild channels: `agent:main:discord:channel:<id>`

Resetting a session creates a new transcript file but keeps the same logical route.

## 8. Useful Commands

```powershell
$env:PYTHONPATH = "src"
python -m agentforge.cli --help
python -m agentforge.cli gateway --help
python -m agentforge.cli gateway run --help
python -m agentforge.cli run --help
```

`agentforge run` is only a deprecated alias for `agentforge gateway run`.

## 9. Troubleshooting

### WebUI opens but there are no models

- check `MODELS_DIR`
- open `http://127.0.0.1:8080/`
- confirm `GET /v1/models` works in the router UI

### WebUI does not auto-open

- set `AUTO_OPEN_BROWSER=1`
- make sure the gateway reaches `/health`

### `run.bat` breaks after editing

- keep CRLF line endings
- avoid saving the file as LF-only

### Port `8080` is busy

- stop the conflicting process
- or override `PORT` in `run.local.bat`

## 10. Validation

```powershell
python -m pytest -q
python -m compileall -q src
$env:PYTHONPATH='src'; python -m agentforge.cli --help
$env:PYTHONPATH='src'; python -m agentforge.cli gateway --help
```
