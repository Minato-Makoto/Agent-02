# Agent-02

Agent-02 is currently a Windows launcher scaffold for `llama-server.exe`.

Current release status:
- the default and only shipped UI is the WebUI served by `llama-server`
- Agent-02 does not ship a custom browser UI
- Agent-02 does not ship a gateway API that re-owns chat, model, or session flow

## What `run.bat` Does

`run.bat` starts `llama-server.exe` directly in router mode and leaves the full chat/model UX to llama itself.

Default local URLs:
- WebUI: `http://127.0.0.1:8080`
- Health: `http://127.0.0.1:8080/health`
- Models: `http://127.0.0.1:8080/models`
- OpenAI-compatible chat: `http://127.0.0.1:8080/v1/chat/completions`

## What Is Not Shipped

This repo intentionally does not ship:
- `/webchat`
- a duplicated copy of the llama WebUI
- an Agent-02 gateway layer for model selection, chat submit, or managed chat sessions

## Local Overrides

Machine-specific overrides belong in `run.local.bat`, copied from `run.local.bat.example`.

Typical overrides:
- `SERVER_EXE`
- `MODELS_DIR`
- `HOST`
- `PORT`
- `MODELS_MAX`
- `CTX_SIZE`
- `GPU_LAYERS`

## Workspace

The workspace directory is still created and kept because later rebuild waves will need project identity and runtime state there.

Current bootstrap files in `workspace/`:
- `IDENTITY.md`
- `SOUL.md`
- `AGENT.md`
- `USER.md`

They are not yet wired into a rebuilt autonomy runtime in this release.

## Roadmap Anchor

The only supported anchor for future rebuild work is the TODO roadmap in `docs/TODO_RUNTIME_DIFF.md`.

The rule is simple:
- if llama already does it, Agent-02 must not re-implement it
- only the post-llama product diff should be built later
