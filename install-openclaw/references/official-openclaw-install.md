# Official OpenClaw install and local-provider anchors

Use these sources to keep installation work aligned with upstream OpenClaw.

## Public docs

- Getting started: `https://docs.openclaw.ai/start/getting-started`
- Source setup: `https://docs.openclaw.ai/start/setup`
- Gateway CLI: `https://docs.openclaw.ai/cli/gateway`
- Control UI: `https://docs.openclaw.ai/web/control-ui`
- vLLM provider: `https://docs.openclaw.ai/providers/vllm`

## Upstream source anchors

- `src/commands/self-hosted-provider-setup.ts`
  - prompts for base URL, API key, and model id
  - writes provider config and auth through OpenClaw's own flow
- `extensions/vllm/index.ts`
  - registers the built-in vLLM plugin
  - documents explicit custom setup and optional discovery
- `src/commands/dashboard.ts`
  - builds the dashboard URL from gateway config and token handling
- `src/config/schema.labels.ts`
  - includes `models.providers.*.apiKey`
- `src/config/schema.help.ts`
  - documents provider auth fields

## Rules for external llama-server

- Treat `llama-server` as an external OpenAI-compatible server.
- Prefer explicit provider setup in OpenClaw:
  - base URL
  - API key
  - model id
- Do not make a launcher own provider state.
- Do not rewrite OpenClaw so it "already knows" the model before provider setup.

## Rules for vLLM auto-discovery

- Auto-discovery is official, but opt-in.
- It requires `VLLM_API_KEY` or an auth profile and no explicit `models.providers.vllm` entry.
- If the user asks for source-faithful explicit setup, prefer explicit provider config instead of discovery.

## Source-install rules

- Keep tailoring outside the repo when possible.
- Use upstream `docs/start/setup.md` for source workflows.
- Use `openclaw setup`, `openclaw gateway`, and `openclaw dashboard` as documented rather than inventing custom boot flows.

## Validation checklist

1. Confirm the installed or checked-out OpenClaw version.
2. Confirm the gateway comes up with the intended bind, port, and auth.
3. Confirm the dashboard opens or prints a valid URL.
4. Confirm the local model server answers `/v1/models`.
5. Confirm OpenClaw provider setup stores the expected provider config.
6. Confirm a real model request succeeds after setup.

