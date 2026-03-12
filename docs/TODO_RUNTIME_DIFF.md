# TODO Runtime Diff

This is the only approved anchor for future implementation work.

## Global Rule

Build only what standalone llama does not already own.

If `llama-server.exe` already handles it, Agent-02 must not duplicate it, proxy it, or wrap it into a second ownership layer.

## Must-Not-Rebuild List

- llama WebUI
- llama chat flow
- llama model loading
- llama model selection
- llama conversation UX
- any second UI that duplicates the above
- any gateway that re-owns the above

## Approved Future Work

1. Workspace bootstrap
- define the project files that should shape the future runtime identity
- clarify how bootstrap content enters the future autonomy runtime
- retained anchors:
  - `workspace/IDENTITY.md`
  - `workspace/SOUL.md`
  - `workspace/AGENT.md`
  - `workspace/USER.md`

2. Autonomy runtime
- planning loop
- durable task state
- background execution
- action gating only where strictly necessary

3. Durable memory beyond context window
- recall and retrieval that do not depend on one transient chat window

4. Channel adapters
- real external communication surfaces
- no policy-first cage on the critical path by default

5. Platform access
- direct capability to interact with external platforms and the open web

6. Human-facing product diff
- only after the runtime diff exists
- only for surfaces llama does not already cover

7. Skill inventory
- decide which future capabilities belong in `skills/`
- keep them as explicit placeholders until implementation starts

8. Tool inventory
- decide which future capabilities belong in `tools/`
- keep them as explicit placeholders until implementation starts

## Repository Rule

This repository should stay docs-first until one future wave is scoped tightly enough to build without drifting back into a llama-duplicating architecture.
