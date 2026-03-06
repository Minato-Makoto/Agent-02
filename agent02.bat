@echo off
title Agent-02 v4.20
color 0B
cd /d "%~dp0"

echo.
echo   Agent-02 v4.20
echo   Private AI gateway for local-first use
echo.

where node >nul 2>nul
if errorlevel 1 (
    echo   [ERROR] Node.js was not found.
    echo   Install Node.js 22+ from https://nodejs.org/
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('node -v') do echo   [OK] Node.js %%v

if not exist "node_modules" (
    echo.
    echo   [*] Installing dependencies...
    call npm install --no-fund --no-audit
    if errorlevel 1 (
        echo   [ERROR] npm install failed.
        pause
        exit /b 1
    )
)

echo.
echo   [*] Building Agent-02...
call npm run build
if errorlevel 1 (
    echo   [ERROR] Build failed.
    pause
    exit /b 1
)

if not exist "data" mkdir data
if not exist "data\workspace" mkdir data\workspace
if not exist "data\instructions" mkdir data\instructions

echo.
echo   [*] Starting Agent-02...
echo.

start /b cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:8420"
node dist/index.js

pause
