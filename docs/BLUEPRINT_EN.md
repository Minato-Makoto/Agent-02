# Blueprint EN

## Repository State

This repository is intentionally reduced to a minimal scaffold.

It now retains only:
- a thin launcher
- agent identity bootstrap markdown files
- skill and tool placeholder directories
- docs and TODO anchors

## Baseline Ownership

`llama-server.exe` owns:
- model loading
- model selection
- chat UX
- WebUI UX

Agent-02 owns none of the above.

## What The Retained Skeleton Means

- launcher: operational anchor only
- workspace bootstrap markdown files: identity anchor only
- skills: future capability inventory anchor
- tools: future capability inventory anchor
- docs: source of truth for rebuild direction

## Non-Negotiable Constraints

- do not duplicate the llama WebUI
- do not reintroduce a second chat UI
- do not wrap model choice in Agent-02
- do not rebuild a gateway that re-owns llama behavior

## Valid Future Work

- workspace identity and bootstrap handling
- autonomy runtime
- durable memory beyond context window
- channel adapters
- platform access
- product surfaces llama does not already cover
