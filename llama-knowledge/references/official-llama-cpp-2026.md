# Official llama.cpp Source Map

Verified against upstream `ggml-org/llama.cpp` on 2026-03-15.

## Table Of Contents

- Source Priority
- Primary URLs
- What Each Source Covers
- Volatile Areas To Re-Check
- Routing Guide

## Source Priority

1. `README.md`
2. task-specific docs under `docs/`
3. `tools/server/README.md` for server flags and HTTP API behavior
4. changelog issues for `llama-server` and `libllama`
5. exact source headers such as `include/llama.h` when the task is library integration

## Primary URLs

- Repo: `https://github.com/ggml-org/llama.cpp`
- README: `https://github.com/ggml-org/llama.cpp/blob/master/README.md`
- Build guide: `https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md`
- Server guide: `https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md`
- Function calling: `https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md`
- Multimodal: `https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md`
- GBNF guide: `https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md`
- OpenCL backend: `https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/OPENCL.md`
- `llama-server` REST API changelog: `https://github.com/ggml-org/llama.cpp/issues/9291`
- `libllama` API changelog: `https://github.com/ggml-org/llama.cpp/issues/9289`

## What Each Source Covers

### README

Use for quick start, install choices, supported backends, GGUF expectations, model download flow, and the canonical split between `llama-cli` and `llama-server`.

Current upstream signals:

- install paths include package managers, Docker, releases, and source builds
- direct model pull via `-hf <user>/<model>[:quant]` is first-class
- GGUF is the required runtime format
- `MODEL_ENDPOINT` can redirect model downloads to another host
- `llama-cli` and `llama-server` examples are the fastest path for basic usage

### Build Guide

Use for local builds and backend selection.

Current upstream build guide is CMake-first and includes dedicated sections for:

- CPU
- BLAS
- Metal
- SYCL
- CUDA
- MUSA
- HIP
- Vulkan
- CANN
- Arm KleidiAI
- OpenCL
- Android
- OpenVINO

Do not guess backend flags. Read the exact backend section for the user's target hardware.

### Server Guide

Use for `llama-server` flags, endpoints, router mode, auth, metrics, slots, and web UI behavior.

Current upstream feature set includes:

- OpenAI-compatible `/v1/completions`
- OpenAI-compatible `/v1/chat/completions`
- OpenAI-compatible `/v1/responses`
- OpenAI-compatible `/v1/embeddings`
- Anthropic-compatible `/v1/messages`
- reranking endpoints
- multimodal support
- schema-constrained JSON output
- function or tool calling
- monitoring endpoints and a built-in web UI

Important framing:

- upstream does not claim full OpenAI or Anthropic parity; it claims practical compatibility
- tool use depends on chat-template support
- `--api-key` and `--api-key-file` exist for auth
- `/health` is public even when API keys are enabled

### Function Calling

Use when the user wants tool use, `tools`, `tool_choice`, or template overrides.

Current upstream rules:

- `llama-server` uses OpenAI-style function calling through the Jinja chat-template path
- native tool formats exist for some model families; other templates fall back to a generic handler
- `--chat-template-file` is the official override when the model metadata template is wrong
- generic handling is less efficient than native formats
- `parallel_tool_calls` is model-dependent and disabled unless requested in the payload

### Multimodal

Use when the user needs image or audio input.

Current upstream rules:

- multimodal input is powered by `libmtmd`
- the supported tools are `llama-mtmd-cli` and `llama-server`
- `llama-server` exposes multimodal through its documented API surface; re-check the server README and REST API changelog for the exact endpoint coverage on the current upstream revision
- enable via `-hf` with a supported model, or pair `-m` with `--mmproj`
- `--no-mmproj` disables the projector for `-hf` loads
- `--no-mmproj-offload` disables projector GPU offload
- audio support is present but still marked highly experimental

### GBNF

Use when the user wants grammar-constrained decoding.

Current upstream position:

- GBNF extends BNF with regex-like features
- grammars are useful for hard output constraints
- sample grammars live under `grammars/`
- for OpenAI-style server integrations, `response_format` JSON or JSON Schema may be simpler than hand-written grammars when the task is just structured JSON

### OpenCL Backend

Use only for OpenCL-specific build or tuning work.

Current upstream OpenCL notes:

- the backend is designed first for Qualcomm Adreno GPUs
- it can also run on some Intel GPUs without SYCL support, but this is not the optimized path
- verified targets include Android, Windows 11 Arm64 on Snapdragon X Elite, and Linux on an Intel test setup
- OpenCL docs explicitly call out `Q4_0` as the optimized quantization and recommend `llama-quantize --pure` for best Adreno performance
- for `gpt-oss` MoE models on this path, upstream recommends the default `MXFP4_MOE` quantization rather than forcing pure `Q4_0`

## Volatile Areas To Re-Check

### `llama-server` REST API Changelog

Re-check `https://github.com/ggml-org/llama.cpp/issues/9291` before giving upgrade or compatibility advice.

Top upstream changes visible on 2026-03-15 include:

- default model name removed and request `"model"` no longer echoed back
- model load and unload endpoints added
- `--jinja` enabled by default
- `/props` gained `model_alias`
- `/metrics` renamed `llamacpp:n_past_max` to `llamacpp:n_tokens_max`
- streamed error events became OpenAI-style
- streamed usage stats now depend on `stream_options.include_usage`
- multimodal support was added to completions and embeddings endpoints

### `libllama` API Changelog

Re-check `https://github.com/ggml-org/llama.cpp/issues/9289` before writing bindings or changing C or C++ integration code.

Top upstream changes visible on 2026-03-15 include:

- pending update to `llama_*_adapter_lora()` APIs
- `llama_params_fit` behavior changed with new device-margin support and enum-style result reporting
- `llama_model_params` gained `use_direct_io`
- new embedding-dimension getters such as `llama_model_n_embd_out`
- backend sampling API additions
- multiple older KV-cache and sampler APIs were removed or renamed in recent releases

## Routing Guide

- "Build llama.cpp on this machine" -> README, `docs/build.md`, then the exact backend doc.
- "Run a GGUF model or convert a checkpoint" -> README sections on GGUF, `-hf`, and quantization.
- "Expose an OpenAI-compatible local API" -> `tools/server/README.md` and the REST API changelog.
- "Why is tool calling failing?" -> `docs/function-calling.md`, the server tool-calling section, and the active chat template.
- "Return strict JSON" -> server `response_format` docs first, then GBNF only if grammar-level control is required.
- "Use images or audio" -> `docs/multimodal.md`.
- "Embed llama.cpp in C or C++" -> `include/llama.h` plus the `libllama` changelog.
