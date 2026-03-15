---
title: Agent-02 Windows Blueprint for OpenClaw and llama.cpp
description: Windows-only blueprint for running Agent-02 with official OpenClaw flows and llama.cpp as an external OpenAI-compatible provider.
---

# Agent-02 Windows Blueprint for OpenClaw and llama.cpp

## Goal

This blueprint rebuilds Agent-02 on native Windows with one clear split:

- OpenClaw remains the only gateway, dashboard, session, channel, node, and tool control plane.
- `llama-server.exe` from `llama.cpp` remains an external OpenAI-compatible model server.
- Provider wiring is done through OpenClaw's built-in setup flow with an explicit base URL, API key, and model id.
- No custom launcher is allowed to preselect models, inject provider state, or rewrite OpenClaw config on behalf of the user.

## Install path chosen

Agent-02 should use the official Windows PowerShell install path for OpenClaw:

1. install OpenClaw with `install.ps1`
2. run `openclaw onboard --flow manual --install-daemon`
3. run `llama-server.exe` as a separate Windows process
4. connect OpenClaw to `llama-server.exe` through OpenClaw's own provider flow

This keeps Windows service/bootstrap behavior, gateway auth, dashboard access, provider setup, and future channel or node setup inside upstream OpenClaw instead of inside repo-local scripts.

## Ownership boundary

### OpenClaw owns

- gateway bind, port, auth token, and daemon lifecycle
- Control UI and dashboard access
- agent sessions, routing, tool use, and usage tracking
- channel login and channel credentials
- node or device pairing and approvals
- web tools, plugins, and optional OpenProse integration
- provider config written under the OpenClaw state directory

### llama.cpp owns

- loading one or more GGUF models
- exposing `/v1/models`
- serving `/v1/chat/completions`
- enforcing the API key used by the local provider

### The repo must not own

- default provider API keys
- default model ids
- hidden provider catalogs
- launcher-generated writes into `%USERPROFILE%\\.openclaw\\openclaw.json`
- launcher-generated writes into agent-local `models.json`

## Windows target layout

Use a normal Windows user profile and keep OpenClaw state in its default home unless isolation is required later.

- OpenClaw config: `%USERPROFILE%\\.openclaw\\openclaw.json`
- OpenClaw workspace: `%USERPROFILE%\\.openclaw\\workspace\\`
- OpenClaw credentials and runtime state: `%USERPROFILE%\\.openclaw\\`
- Local models: `D:\\Models\\`
- Optional source checkout for `llama.cpp`: `D:\\src\\llama.cpp\\`

No repo-local runtime state is required for the standard install.

## Step 1: Install OpenClaw on Windows

Open a normal PowerShell session and run the official installer:

```powershell
iwr -useb https://openclaw.ai/install.ps1 | iex
openclaw doctor
```

Expected result:

- OpenClaw CLI is on `PATH`
- Node.js is available if the installer had to bootstrap it
- `openclaw doctor` reports a usable local install

## Step 2: Create the local Agent-02 gateway

Run the onboarding flow in manual mode so gateway auth and startup behavior stay explicit:

```powershell
openclaw onboard --flow manual --install-daemon
```

During onboarding, keep these Windows-local decisions:

- gateway mode: local
- bind address: loopback only
- auth: token enabled
- daemon install: enabled
- workspace: keep the default OpenClaw workspace unless you have a separate Windows profile for Agent-02

If the wizard offers model setup before `llama-server.exe` is ready, skip that part for now and return to it after Step 5.

After onboarding, verify the service side first:

```powershell
openclaw gateway status
openclaw dashboard
```

`openclaw dashboard` should print or open the local Control UI URL for the gateway you just created.

## Step 3: Install llama.cpp on Windows

### Recommended path: prebuilt Windows package

Use the official Windows package first:

```powershell
winget install llama.cpp
Get-Command llama-server
```

### Optional path: build from source on Windows

Use this only if you need a specific backend or you want to pin a source checkout:

```powershell
git clone https://github.com/ggml-org/llama.cpp.git D:\src\llama.cpp
cd D:\src\llama.cpp
cmake -B build
cmake --build build --config Release
```

For a GPU build, add the Windows backend you actually use, such as `-DGGML_CUDA=ON` or `-DGGML_VULKAN=ON`, before the build step.

## Step 4: Prepare the local model

Place the GGUF model that Agent-02 should use under a normal Windows path, for example:

```powershell
New-Item -ItemType Directory -Force D:\Models | Out-Null
```

Recommended model rules:

- use an instruct or chat GGUF, not a raw base model
- prefer a model that already includes the correct chat template
- if your chosen model needs an explicit template, pass the matching llama.cpp template flags when you start the server

## Step 5: Start `llama-server.exe`

Keep the model server local and authenticated. Example:

```powershell
$env:LLAMA_SERVER_API_KEY = "agent02-local"
$ModelPath = "D:\Models\qwen2.5-coder-7b-instruct-q4_k_m.gguf"

llama-server.exe `
  -m $ModelPath `
  --host 127.0.0.1 `
  --port 8080 `
  --api-key $env:LLAMA_SERVER_API_KEY
```

Validate the provider surface before touching OpenClaw model settings:

```powershell
$headers = @{ Authorization = "Bearer $env:LLAMA_SERVER_API_KEY" }
Invoke-RestMethod -Headers $headers -Uri "http://127.0.0.1:8080/v1/models"
```

Use the exact returned model id in the next step.

## Step 6: Register `llama-server.exe` inside OpenClaw

Do not hand-edit OpenClaw config unless you are recovering from a broken install. Use OpenClaw's own setup flow.

Recommended options:

- reopen `openclaw onboard` if you intentionally skipped model setup earlier
- or run `openclaw configure` and complete the model or provider section there
- or open the Control UI config screen from the dashboard and use the built-in provider setup

The values must be explicit:

- provider type: self-hosted OpenAI-compatible or vLLM-style explicit provider setup
- base URL: `http://127.0.0.1:8080/v1`
- API key: the same value used in `llama-server.exe --api-key`
- model id: the exact id returned by `GET /v1/models`

Once the provider exists, confirm the model is visible to OpenClaw:

```powershell
openclaw models list
```

If you want Agent-02 to prefer this model by default, set it with the exact provider and model id that OpenClaw exposes:

```powershell
openclaw models set <provider>/<model-id>
```

Replace `<provider>/<model-id>` with the exact value shown by `openclaw models list`.

## Step 7: Use OpenClaw as the only front door

After provider setup, use OpenClaw features through OpenClaw, not by sending traffic directly to `llama-server.exe`.

### Control UI

- launch with `openclaw dashboard`
- sign in with the gateway token if prompted
- verify chat responses stream through the local provider

### Channels

- log into supported channels with `openclaw channels login`
- keep all channel credentials in OpenClaw state, never in llama.cpp launch scripts

### Nodes and devices

- inspect device state with `openclaw devices list`
- approve pending devices with `openclaw devices approve <id>`
- inspect node connectivity with `openclaw nodes status`

### Web tools and plugins

- configure web search or browser tooling with `openclaw configure --section web`
- enable OpenProse only through OpenClaw plugins: `openclaw plugins enable open-prose`
- restart the gateway after plugin changes if OpenClaw requests it

## Full-feature expectation

Using `llama-server.exe` as the local model backend must not reduce OpenClaw to a thin chat shell.

The supported expectation for Agent-02 is:

- local model inference comes from llama.cpp
- gateway auth and dashboard stay in OpenClaw
- sessions, routing, and tools stay in OpenClaw
- channel integrations stay in OpenClaw
- nodes, approvals, and device trust stay in OpenClaw
- model selection stays in OpenClaw after the provider is registered

## Forbidden drift

Do not reintroduce any of the following:

- a repo-local launcher that injects `VLLM_API_KEY` or equivalent provider state behind OpenClaw's back
- `MODEL_PATH`, `DEFAULT_MODEL_ID`, or `MODELS_DIR` as policy layers that select models for OpenClaw
- auto-generated writes into OpenClaw config from repo scripts
- direct channel, node, or dashboard traffic to `llama-server.exe`
- storing the gateway token inside the llama.cpp startup command
- binding either service to a public interface before auth is intentionally configured

## Validation checklist

Run this checklist in order:

1. `openclaw doctor` passes.
2. `openclaw gateway status` shows the local gateway is installed and reachable.
3. `openclaw dashboard` opens the local Control UI URL.
4. `Invoke-RestMethod http://127.0.0.1:8080/v1/models` succeeds with the llama.cpp API key.
5. `openclaw models list` shows the configured local provider model.
6. `openclaw models set ...` succeeds for the intended Agent-02 model.
7. A real chat in Control UI streams a response from the local model.
8. If channels are required, `openclaw channels login` succeeds and channel activity still routes through OpenClaw.
9. If nodes or devices are required, `openclaw devices list` and `openclaw nodes status` show healthy state.
10. If web tools or OpenProse are required, they are enabled through `openclaw configure` or `openclaw plugins`, then rechecked from the dashboard.

## Source anchors

OpenClaw references:

- Getting started: https://docs.openclaw.ai/start/getting-started
- Source setup: https://docs.openclaw.ai/start/setup
- Gateway CLI: https://docs.openclaw.ai/cli/gateway
- Onboarding CLI: https://docs.openclaw.ai/cli/onboard
- Configure CLI: https://docs.openclaw.ai/cli/configure
- Control UI: https://docs.openclaw.ai/web/control-ui
- vLLM provider: https://docs.openclaw.ai/providers/vllm
- Source anchor: `src/commands/self-hosted-provider-setup.ts`
- Source anchor: `extensions/vllm/index.ts`
- Source anchor: `src/commands/dashboard.ts`

llama.cpp references:

- Install on Windows: https://github.com/ggml-org/llama.cpp/blob/master/docs/install.md
- Build on Windows: https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md
- Server API: https://github.com/ggml-org/llama.cpp/blob/master/examples/server/README.md
