@echo off
setlocal EnableExtensions
pushd "%~dp0"
if errorlevel 1 (
    echo ERROR: cannot access repository directory.
    exit /b 1
)

set "PYTHONPATH=%~dp0src"

REM Local overrides (do not commit): put secrets and machine-specific paths in run.local.bat
if exist "%~dp0run.local.bat" (
    call "%~dp0run.local.bat"
)

REM ============================================================
REM Agent-02 launcher (Windows) - direct llama-server mode
REM
REM Default behavior:
REM   - Starts llama-server in router mode on port 8080
REM   - Uses the llama WebUI at http://127.0.0.1:8080
REM   - Does not boot any Agent-02 gateway or duplicate UI
REM ============================================================

if not defined SERVER_EXE set "SERVER_EXE=%~dp0..\llama.cpp\llama-server.exe"
if not defined MODELS_DIR set "MODELS_DIR=%~dp0..\models"
if not defined HOST set "HOST=127.0.0.1"
if not defined PORT set "PORT=8080"
if not defined MODELS_MAX set "MODELS_MAX=1"
if not defined CTX_SIZE set "CTX_SIZE=16384"
if not defined GPU_LAYERS set "GPU_LAYERS=-1"
if not defined THREADS set "THREADS=0"
if not defined TEMPERATURE set "TEMPERATURE=0.1"
if not defined TOP_P set "TOP_P=0.9"
if not defined TOP_K set "TOP_K=40"
if not defined REPEAT_PENALTY set "REPEAT_PENALTY=1.1"
if not defined SEED set "SEED=-1"
if not defined MAX_TOKENS set "MAX_TOKENS=8192"
if not defined BOOT_TIMEOUT set "BOOT_TIMEOUT=120"
if not defined SHUTDOWN_TIMEOUT set "SHUTDOWN_TIMEOUT=5"
if not defined WORKSPACE set "WORKSPACE=%~dp0workspace"
if not defined EXTRA_ARGS set "EXTRA_ARGS="
if not defined AGENTFORGE_BROWSER_HEADLESS set "AGENTFORGE_BROWSER_HEADLESS=0"
if not defined AGENTFORGE_DESKTOP_CONTROL set "AGENTFORGE_DESKTOP_CONTROL=1"
if not defined TOOL_TIMEOUT_BROWSER_NAV_MS set "TOOL_TIMEOUT_BROWSER_NAV_MS=60000"
if not defined TOOL_TIMEOUT_BROWSER_ACTION_MS set "TOOL_TIMEOUT_BROWSER_ACTION_MS=15000"
if not defined TOOL_TIMEOUT_BROWSER_WAIT_MS set "TOOL_TIMEOUT_BROWSER_WAIT_MS=30000"
if not defined TOOL_TIMEOUT_DESKTOP_ACTION_MS set "TOOL_TIMEOUT_DESKTOP_ACTION_MS=5000"
if not defined TOOL_TIMEOUT_DESKTOP_SCREENSHOT_S set "TOOL_TIMEOUT_DESKTOP_SCREENSHOT_S=15"
if not defined TOOL_TIMEOUT_WEB_REQUEST_S set "TOOL_TIMEOUT_WEB_REQUEST_S=30"
if not defined TOOL_TIMEOUT_WEB_SEARCH_S set "TOOL_TIMEOUT_WEB_SEARCH_S=15"
if not defined TOOL_TIMEOUT_PHOTOSHOP_S set "TOOL_TIMEOUT_PHOTOSHOP_S=30"
if not defined TOOL_TIMEOUT_PROCESS_LIST_S set "TOOL_TIMEOUT_PROCESS_LIST_S=10"
if not defined SHELL_WORKSPACE_ONLY set "SHELL_WORKSPACE_ONLY=1"

set "SERVER_EXE=%SERVER_EXE:"=%"
set "MODELS_DIR=%MODELS_DIR:"=%"
set "WORKSPACE=%WORKSPACE:"=%"

if not exist "%WORKSPACE%" (
    mkdir "%WORKSPACE%" >nul 2>&1
    if errorlevel 1 (
        echo ERROR: cannot create workspace directory: %WORKSPACE%
        goto :fail
    )
)

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python was not found in PATH.
    echo Install Python 3.10+ and try again.
    goto :fail
)

python -c "import requests" >nul 2>&1
if errorlevel 1 (
    echo Installing Python packages from requirements.txt...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: failed to install dependencies.
        goto :fail
    )
)

echo ============================================================
echo  Agent-02 Launcher
echo  llama-server: http://%HOST%:%PORT%
echo  Health:       http://%HOST%:%PORT%/health
echo  WebUI:        http://%HOST%:%PORT%
echo ============================================================

python -m agentforge.cli run ^
  --server-exe "%SERVER_EXE%" ^
  --models-dir "%MODELS_DIR%" ^
  --models-max %MODELS_MAX% ^
  --host "%HOST%" ^
  --port %PORT% ^
  --ctx-size %CTX_SIZE% ^
  --gpu-layers %GPU_LAYERS% ^
  --threads %THREADS% ^
  --temp %TEMPERATURE% ^
  --top-p %TOP_P% ^
  --top-k %TOP_K% ^
  --repeat-penalty %REPEAT_PENALTY% ^
  --seed %SEED% ^
  --max-tokens %MAX_TOKENS% ^
  --boot-timeout %BOOT_TIMEOUT% ^
  --shutdown-timeout %SHUTDOWN_TIMEOUT% ^
  --workspace "%WORKSPACE%" ^
  %EXTRA_ARGS%
set "EXIT_CODE=%ERRORLEVEL%"
goto :end

:fail
set "EXIT_CODE=1"
if not defined CI (
    if /I not "%AGENTFORGE_NO_PAUSE_ON_FAIL%"=="1" (
        echo.
        echo Failed to start Agent-02. Press any key to close the window...
        pause >nul
    )
)

:end
popd
exit /b %EXIT_CODE%
