# ? Agent-02 — Self-Hosted AI Gateway (Secure Edition 2026)

**One command. Your AI. Your rules. 100% private & secure.**

Agent-02 connects official messaging APIs to modern AI models (cloud or local `.gguf`) through a gateway running on your own machine.

---

## ?? Quick Start (T?t c? OS)

```bash
curl -fsSL https://raw.githubusercontent.com/yourname/agent-02/main/install.sh | bash
agent02 start
```

Browser opens `http://localhost:8080` with the Control UI.

---

## ?? K?t n?i Platforms (CH? OFFICIAL)

| Platform | Cách k?t n?i chính th?c |
|---|---|
| Telegram | Bot API + BotFather token |
| WhatsApp | WhatsApp Business API / Cloud API |
| Discord | Discord Bot + Interactions API |
| Slack | Slack App + OAuth |
| Microsoft Teams | Microsoft Graph + OAuth |
| Matrix / Google Chat | Official SDK |

Current built-in connectors in this repo: Telegram, WhatsApp Cloud API, Discord.

---

## ?? Supported AI Models

- Cloud: OpenAI, Anthropic Claude 4, Google Gemini, Grok 4, DeepSeek, Qwen (OpenAI-compatible routing)
- Local: `llama.cpp` (OpenAI-compatible server), Ollama, vLLM (GGUF offline-ready)

---

## ??? Built-in Skills (Sandbox + Explicit Consent)

- Notes & Tasks (`notes` skill)
- Consent queue for high-impact actions
- API-first skill runtime (deny-by-default for actions requiring approval)

All sensitive actions require explicit user approval in Control UI.

---

## ??? Project Structure (New)

```text
agent-02/
+-- install.sh
+-- agent02                    # launcher / single-binary entry
+-- cmd/
¦   +-- agent02/
¦       +-- main.go            # CLI: start, connect, skills enable
+-- src/
¦   +-- gateway/               # Core router + runtime bootstrap
¦   +-- adapters/              # Official connectors only
¦   +-- llm/                   # Cloud + local model routing
¦   +-- skills/                # Sandboxed tools + consent workflow
¦   +-- api/                   # Secure REST + webhook endpoints
¦   +-- security/              # Encryption + signature verification
¦   +-- store/                 # SQLite + config persistence
¦   +-- config/                # Config schema/defaults
+-- ui/                        # Tauri 2.0 + React control UI
+-- data/                      # SQLite + encrypted secrets (runtime)
+-- tests/
¦   +-- integration/
+-- Dockerfile
+-- docker-compose.yml
+-- go.mod
+-- README.md
```

---

## ?? Security Defaults

- Official APIs only (no WhatsApp Web automation, no unofficial hijack connectors)
- Encrypted secrets at rest using AES-GCM (`data/config.json` encrypted fields)
- Webhook signature verification:
  - Telegram secret token header
  - WhatsApp `X-Hub-Signature-256` HMAC
  - Discord `X-Signature-Ed25519`
- Admin API token required by default (`X-Agent02-Token`)
- Strict request limits, secure headers, and least-privilege skill model

---

## ?? CLI Usage

```bash
# Start gateway
agent02 start --data-dir ./data

# Connect official platforms
agent02 connect telegram --token <TOKEN> --webhook-secret <SECRET> --enable
agent02 connect whatsapp --phone-number-id <ID> --access-token <TOKEN> --app-secret <SECRET> --verify-token <VERIFY> --enable
agent02 connect discord --token <TOKEN> --application-id <APP_ID> --public-key <PUBKEY> --enable

# Enable/disable skills
agent02 skills enable --skill notes --on true
```

---

## ?? Docker

```bash
docker compose up -d
# Optional local GGUF inference server
docker compose --profile local-gguf up -d llama-cpp
```

---

## ?? Integration Safety Scenario

See:
- `tests/integration/telegram_local_gguf_notes_consent.md`

Scenario validates:
1. Telegram webhook via official API
2. Local GGUF inference via `llama.cpp`
3. Notes skill requiring explicit consent before write

---

## Notes

- `signal-cli` is intentionally not integrated as a first-party official connector path in this secure profile.
- `whatsapp-web.js` is intentionally excluded because the secure edition enforces official WhatsApp Business/Cloud API only.