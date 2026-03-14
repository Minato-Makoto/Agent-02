---
title: "Model Selection"
description: "How Agent-02 finds GGUF models through llama-server and chooses the default OpenClaw model."
---

# Model Selection

[Vietnamese version](../vi/models)

Agent-02 uses `llama-server` router mode and reads the live model list from:

`http://127.0.0.1:8000/v1/models`

## Model Files

- Put `.gguf` files in `..\\models\\` by default.
- Change `MODELS_DIR` in `run.local.bat` if your models live elsewhere.

## Default Model Resolution

- If `DEFAULT_MODEL_ID` is set, the launcher validates it against `/v1/models` and uses it.
- If `DEFAULT_MODEL_ID` is empty, the launcher picks the first model ID in stable alphabetical order.
- OpenClaw then uses `vllm/<model-id>` as the default primary model.

## Important Behavior

- The launcher does not hardcode a context window.
- The launcher does not hardcode an output token limit.
- Runtime behavior is delegated to the selected model and `llama-server`.
