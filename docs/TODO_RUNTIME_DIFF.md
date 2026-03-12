# TODO Runtime Diff

This file is the only approved anchor for future rebuild work.

Build only what standalone llama does not already own.

## Rules

- Do not duplicate the llama WebUI.
- Do not add a custom Agent-02 model picker on top of llama.
- Do not reintroduce a gateway that owns chat, model, or session semantics.
- Only build product-diff capability after the baseline remains llama-first.

## Future Diff Buckets

1. Workspace bootstrap
- define how `IDENTITY.md`, `SOUL.md`, `AGENT.md`, and `USER.md` feed the rebuilt runtime

2. Autonomy runtime
- planning loop
- durable task state
- background execution
- approvals only where truly needed

3. Durable memory beyond context window
- retrieval and recall that is not limited to a single transcript window

4. Channel adapters
- external messaging surfaces as real runtime capabilities
- no policy-first cage on the critical path by default

5. Platform access
- external web and platform access as part of the agent runtime surface

6. Human-facing product diff
- only after the above exists
- only for capability surfaces that llama WebUI does not already cover
