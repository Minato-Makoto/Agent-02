@echo off
title Agent-02 Secure AI Gateway
color 0B

:: Navigate to the directory where this .bat file lives
cd /d "%~dp0"

echo.
echo   ======================================
echo   Agent-02 -- Self-Hosted AI Gateway
echo   Secure Edition 2026
echo   ======================================
echo.

:: ── Check Node.js ──
where node >nul 2>nul
if errorlevel 1 (
    echo   [ERROR] Node.js not found!
    echo   Download: https://nodejs.org/en/download/
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('node -v') do echo   [OK] Node.js %%v

:: ── Install Dependencies ──
if not exist "node_modules" (
    echo.
    echo   [*] Installing dependencies...
    call npm install --no-fund --no-audit
    if errorlevel 1 (
        echo   [ERROR] npm install failed!
        pause
        exit /b 1
    )
    echo   [OK] Dependencies installed
)

:: ── Build TypeScript ──
if not exist "dist" (
    echo.
    echo   [*] Building TypeScript...
    call npx --yes tsc -p tsconfig.json
    if errorlevel 1 (
        echo   [ERROR] TypeScript build failed!
        pause
        exit /b 1
    )
    echo   [OK] Build complete
)

:: ── Create data directories ──
if not exist "data" mkdir data
if not exist "data\workspace" mkdir data\workspace

:: ── Start Server ──
echo.
echo   [*] Starting Agent-02...
echo.

:: Open browser after 2 seconds
start /b cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8080"

:: Run the server
node dist/index.js

pause
