# Agent-02

Agent-02 is now a minimal skeleton repository.

Current state:
- a thin launcher that starts `llama-server`
- no shipped custom runtime beyond that launcher
- no shipped custom UI
- no shipped skill or tool implementations
- retained identity bootstrap markdown files
- docs and TODO anchors for future rebuild work

## What Remains

Minimal retained anchors:
- `run.bat`
- `run.local.bat.example`
- `src/agentforge/cli.py`
- `workspace/IDENTITY.md`
- `workspace/SOUL.md`
- `workspace/AGENT.md`
- `workspace/USER.md`
- `skills/`
- `tools/`
- `docs/`

## Current Rule

`llama-server` owns runtime and UI behavior.

Agent-02 must not rebuild:
- llama WebUI
- model selection
- chat flow
- conversation UX

## What The Launcher Is Allowed To Do

Only:
- resolve local paths
- create workspace directory if needed
- start `llama-server`

It must not own chat, model, session, or policy semantics.

## Identity Bootstrap Files

The following markdown files are intentionally retained as future runtime anchors:
- `workspace/IDENTITY.md`
- `workspace/SOUL.md`
- `workspace/AGENT.md`
- `workspace/USER.md`

They are placeholders today, but they remain in-repo so future work has concrete identity inputs to build from.

## What Skills And Tools Mean Right Now

The `skills/` and `tools/` directories are placeholders only.

They exist so future work has concrete anchors, but nothing there is implemented yet.

## Canon Docs

Use these files as the current source of truth:
- `docs/TODO_RUNTIME_DIFF.md`
- `docs/BLUEPRINT_EN.md`
- `docs/BLUEPRINT_VI.md`
- `docs/TUTORIAL_EN.md`
- `docs/TUTORIAL_VI.md`
