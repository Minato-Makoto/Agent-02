---
name: llama-knowledge
description: Official llama.cpp knowledge and workflow for current upstream documentation, source behavior, and API changes. Use when Codex needs to answer questions about llama.cpp, build or run llama.cpp locally, work with GGUF models, configure llama-cli or llama-server, implement OpenAI-compatible API usage, function or tool calling, structured outputs, multimodal input, GBNF grammars, backend-specific builds such as OpenCL/CUDA/Metal/Vulkan, or verify whether a llama.cpp behavior changed recently upstream.
---

# Llama Knowledge

Read `references/official-llama-cpp-2026.md` before making recommendations. It maps the current upstream docs as verified on 2026-03-15 and marks the fast-moving areas that must be re-checked.

## Workflow

1. Classify the task before answering.
- Build, install, or local runtime: start with `README.md` and `docs/build.md`.
- Model download, GGUF conversion, or quantization: start with the README sections on GGUF and model acquisition.
- HTTP serving, API compatibility, router mode, auth, metrics, or web UI: start with `tools/server/README.md`.
- Function or tool calling: read `docs/function-calling.md` and the matching `llama-server` tool-calling section.
- Multimodal requests: read `docs/multimodal.md` and the relevant `llama-server` endpoint section.
- Grammar-constrained output: read `grammars/README.md`; for OpenAI-style JSON output, also check `response_format` in `tools/server/README.md`.
- C or C++ embedding work: read `include/llama.h` and the `libllama` changelog.
- Backend-specific performance or build work: read the exact backend doc, such as `docs/backend/OPENCL.md`.

2. Prefer upstream sources over memory.
- Use `ggml-org/llama.cpp` docs, source files, and changelog issues as the source of truth.
- Treat community blog posts, mirrors, old snippets, and outdated repo paths as secondary unless they still match current upstream.
- When the user asks for the latest or current behavior, re-check the relevant upstream doc or changelog before answering.

3. Keep boundaries explicit.
- Distinguish `llama-cli`, `llama-server`, `libllama`, `llama-quantize`, and backend docs.
- Distinguish practical OpenAI or Anthropic compatibility from full API parity.
- Distinguish model or chat-template limitations from server feature limitations.

4. Surface volatility when it matters.
- Re-check the `llama-server` REST API changelog before making endpoint or payload guarantees.
- Re-check the `libllama` API changelog before making C or C++ integration guarantees.
- Include exact dates when clarifying "latest", "today", or "current" behavior.

## Guardrails

- Do not claim full OpenAI API compatibility when upstream explicitly frames it as practical compatibility.
- Do not assume tool calling works the same on every model; native vs generic chat-template handling matters.
- Do not recommend multimodal flags without checking `--mmproj`, `--no-mmproj`, and `--no-mmproj-offload`.
- Do not give backend build flags from memory when a backend-specific doc exists.
- Do not mix server flags into `llama-cli` guidance or library guidance.

## Deliverables

When this skill is used, produce:

- the exact upstream sources used
- the selected workflow path and why it matches the task
- commands, code, or config aligned with the current upstream docs
- a volatility note when the answer depends on the changelog-tracked API surface
