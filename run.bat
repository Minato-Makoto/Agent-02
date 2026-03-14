@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
pushd "%ROOT%" >nul || (
  echo Failed to enter %ROOT%
  exit /b 1
)
set "PNPM_SHIM_DIR=%TEMP%\agent02-pnpm-shim"
if not exist "%PNPM_SHIM_DIR%" mkdir "%PNPM_SHIM_DIR%" >nul 2>&1
(
  echo @echo off
  echo call corepack pnpm %%*
  echo exit /b %%errorlevel%%
) > "%PNPM_SHIM_DIR%\pnpm.cmd"
set "PATH=%PNPM_SHIM_DIR%;%PATH%"

if exist "%ROOT%run.local.bat" call "%ROOT%run.local.bat"

if not defined LLAMA_SERVER_EXE set "LLAMA_SERVER_EXE=%ROOT%..\llama.cpp\llama-server.exe"
if not defined MODELS_DIR set "MODELS_DIR=%ROOT%..\models"
set "LLAMA_PORT=8000"
if not defined GATEWAY_PORT set "GATEWAY_PORT=18789"
if not defined OPEN_LLAMA_UI set "OPEN_LLAMA_UI=0"
if not defined OPENCLAW_STATE_DIR set "OPENCLAW_STATE_DIR=%ROOT%.openclaw"
if not defined OPENCLAW_CONFIG_PATH set "OPENCLAW_CONFIG_PATH=%OPENCLAW_STATE_DIR%\openclaw.json"

set "OPENCLAW_GATEWAY_PORT=%GATEWAY_PORT%"
set "VLLM_API_KEY=vllm-local"

where node >nul 2>&1 || (
  echo Node.js was not found in PATH.
  popd
  exit /b 1
)

where corepack >nul 2>&1 || (
  echo Corepack was not found in PATH.
  popd
  exit /b 1
)

if not exist "%ROOT%node_modules" (
  echo Installing dependencies...
  call corepack pnpm install
  if errorlevel 1 (
    echo pnpm install failed. Trying approve-builds once...
    call corepack pnpm approve-builds
    if errorlevel 1 (
      popd
      exit /b 1
    )
    call corepack pnpm install
    if errorlevel 1 (
      popd
      exit /b 1
    )
  )
)

if not exist "%ROOT%dist\entry.js" (
  echo Building OpenClaw...
  call corepack pnpm ui:build
  if errorlevel 1 (
    popd
    exit /b 1
  )
  call corepack pnpm build
  if errorlevel 1 (
    popd
    exit /b 1
  )
)

node "%ROOT%scripts\agent02-launcher.mjs"
if errorlevel 1 (
  popd
  exit /b 1
)

if /I "%OPEN_LLAMA_UI%"=="1" start "" "http://127.0.0.1:8000/"

node "%ROOT%openclaw.mjs" dashboard
if errorlevel 1 (
  popd
  exit /b 1
)

popd
endlocal
exit /b 0
