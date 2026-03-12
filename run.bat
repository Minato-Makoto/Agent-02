@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHONPATH=%ROOT%src"

set "SERVER_EXE=%ROOT%..\llama.cpp\llama-server.exe"
set "MODELS_DIR=%ROOT%..\models"
set "HOST=127.0.0.1"
set "PORT=8080"
set "WORKSPACE=%ROOT%workspace"
set "EXTRA_ARGS="

if exist "%ROOT%run.local.bat" call "%ROOT%run.local.bat"

python -m agentforge.cli run ^
  --server-exe "%SERVER_EXE%" ^
  --models-dir "%MODELS_DIR%" ^
  --host "%HOST%" ^
  --port "%PORT%" ^
  --workspace "%WORKSPACE%" ^
  %EXTRA_ARGS%

endlocal
