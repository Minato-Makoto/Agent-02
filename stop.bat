@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
pushd "%ROOT%" >nul || (
  echo Failed to enter %ROOT%
  exit /b 1
)

if exist "%ROOT%run.local.bat" call "%ROOT%run.local.bat"

set "LLAMA_PORT=8000"
if not defined GATEWAY_PORT set "GATEWAY_PORT=18789"

where node >nul 2>&1 || (
  echo Node.js was not found in PATH.
  popd
  exit /b 1
)

node "%ROOT%scripts\agent02-stop.mjs"
if errorlevel 1 (
  popd
  exit /b 1
)

popd
endlocal
exit /b 0
