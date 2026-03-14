---
title: "Model Selection"
description: "Agent-02 đọc danh sách GGUF từ llama-server và chọn model mặc định cho OpenClaw như thế nào."
---

# Model Selection

[English version](../en/models)

Agent-02 dùng router mode của `llama-server` và đọc model list live từ:

`http://127.0.0.1:8000/v1/models`

## File Model

- Đặt file `.gguf` vào `..\\models\\` theo mặc định.
- Đổi `MODELS_DIR` trong `run.local.bat` nếu model nằm ở nơi khác.

## Cách Chọn Model Mặc Định

- Nếu `DEFAULT_MODEL_ID` được set, launcher sẽ validate với `/v1/models` và dùng model đó.
- Nếu `DEFAULT_MODEL_ID` để trống, launcher sẽ lấy model ID đầu tiên theo thứ tự alphabet ổn định.
- Sau đó OpenClaw dùng `vllm/<model-id>` làm primary model mặc định.

## Hành Vi Quan Trọng

- Launcher không hardcode context window.
- Launcher không hardcode output token limit.
- Runtime thật sự do model được chọn và `llama-server` quyết định.
