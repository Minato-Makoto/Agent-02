# Integration Scenario: Telegram + local GGUF + Notes Consent

## Goal
Verify that Agent-02 processes Telegram messages with local `llama.cpp` (`.gguf`) while enforcing explicit consent for the Notes skill.

## Preconditions
1. Agent-02 started: `agent02 start --data-dir ./data`.
2. `llama.cpp` server running at `http://127.0.0.1:8081` with OpenAI-compatible endpoint.
3. Telegram connector configured with official Bot API token and webhook secret:
   - `agent02 connect telegram --token <TOKEN> --webhook-secret <SECRET> --enable`
4. LLM config points to local provider (`provider=llama.cpp`, base URL `http://127.0.0.1:8081`).
5. Admin token available from first startup output.

## Test Flow
1. Send `/note add buy milk` to Telegram bot.
2. Expected immediate bot response: `Consent required... ID: <uuid>`.
3. In Control UI (`http://localhost:8080`), open Pending Consents and approve the matching ID.
4. Send `/note list` to Telegram bot.
5. Expected bot response includes `buy milk`.
6. Send a normal prompt (e.g., `summarize zero trust in one paragraph`).
7. Expected response comes from local GGUF model and does not require consent.

## Security Assertions
1. Webhook authentication:
   - Telegram secret header mismatch returns `401`.
2. Consent enforcement:
   - `notes.add` cannot execute without explicit approval.
3. Least privilege:
   - No filesystem/shell execution path is available in this scenario.
4. Secret hygiene:
   - Connector tokens are stored encrypted in `data/config.json`.

## Negative Cases
1. Deny the pending consent and verify `/note list` does not include denied note.
2. Remove `X-Agent02-Token` and verify `/api/consents` is blocked when admin auth is enabled.
3. Stop `llama.cpp` and verify chat returns safe gateway error without crash.