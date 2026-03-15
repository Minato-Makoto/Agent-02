---
name: install-openclaw
description: Install, reinstall, or reconnect OpenClaw using official upstream docs and source behavior. Use when Codex needs to set up OpenClaw from scratch, run it from source, wire an external OpenAI-compatible model server such as llama-server or vLLM, build a thin launcher around OpenClaw without changing OpenClaw semantics, or audit an existing install against the official gateway, dashboard, and provider setup flows.
---

# Install OpenClaw

Read `references/official-openclaw-install.md` before making changes. It contains the official docs URLs, the upstream source anchors, and the local-provider rules this skill must follow.

## Workflow

1. Identify the requested mode before changing anything.
- Official install path: follow the current public docs for install, onboarding, gateway, and dashboard.
- Source checkout path: follow upstream `docs/start/setup.md`.
- Local model-server integration path: treat `llama-server` or vLLM as an external OpenAI-compatible `/v1` server.
- Fork audit path: compare the current install against upstream provider and gateway flows before fixing.

2. Keep OpenClaw semantics upstream-first.
- Use upstream docs and source as the source of truth.
- Prefer the built-in provider setup flow over custom launcher-owned configuration.
- Treat local wrappers, env injection, or config mutation as drift unless the upstream docs or source explicitly support them.

3. Configure local model servers the way OpenClaw already supports.
- For an external OpenAI-compatible server, configure OpenClaw with base URL, API key, and model id.
- Use the vLLM/self-hosted provider flow as the closest official path for `llama-server`.
- Only use vLLM auto-discovery when the user explicitly wants that official behavior. Do not invent hidden autodiscovery.

4. Keep launchers thin.
- Launchers may start processes and print connection details.
- Launchers may read user-owned config.
- Launchers must not rewrite `.openclaw/openclaw.json`, choose default models on behalf of OpenClaw, inject provider semantics, or create shadow provider state.

5. Validate from the outside in.
- Verify the model server exposes the expected `/v1` endpoints.
- Verify OpenClaw gateway starts with the expected auth and dashboard behavior.
- Verify provider setup succeeds through OpenClaw itself.
- Verify a real model call works after provider setup.

## Guardrails

- Do not rewrite OpenClaw internals to accommodate a launcher.
- Do not treat the chat model picker as the place to enter provider API keys.
- Do not conflate OpenClaw multi-model behavior with how `llama-server` happens to host models.
- Do not reuse contaminated runtime state when the task is a reinstall or source-fidelity audit.

## Deliverables

When this skill is used, produce:

- the chosen install path and why it matches official OpenClaw behavior
- the exact commands or file edits needed
- the validation steps and the source anchors used

