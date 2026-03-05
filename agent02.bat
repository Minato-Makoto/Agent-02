@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

set "DATA_DIR=%~dp0data"
set "BIN_DIR=%~dp0bin"
set "BIN=%BIN_DIR%\agent02.exe"
set "ROOT_BIN=%~dp0agent02.exe"
set "REPO=%AGENT02_REPO%"

if "%REPO%"=="" (
  for /f "delims=" %%G in ('git config --get remote.origin.url 2^>nul') do (
    set "REPO=%%G"
  )
  if defined REPO (
    set "REPO=!REPO:.git=!"
    set "REPO=!REPO:https://github.com/=!"
    set "REPO=!REPO:http://github.com/=!"
    set "REPO=!REPO:git@github.com:=!"
    set "REPO=!REPO:\=/!"
  )
)
if "%REPO%"=="" set "REPO=yourname/agent-02"

set "ARCH=amd64"
if /I "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "ARCH=arm64"
if /I "%PROCESSOR_ARCHITEW6432%"=="ARM64" set "ARCH=arm64"

if not exist "%BIN_DIR%" mkdir "%BIN_DIR%"

if exist "%BIN%" goto RUN
if exist "%ROOT_BIN%" (
  set "BIN=%ROOT_BIN%"
  goto RUN
)

call :DOWNLOAD_PREBUILT
if %errorlevel%==0 goto RUN

where go >nul 2>nul
if %errorlevel% neq 0 goto NO_GO

echo [agent02] Building Windows binary...
set "CGO_ENABLED=0"
go build -trimpath -ldflags="-s -w" -o "%BIN%" .\cmd\agent02
if %errorlevel% neq 0 goto BUILD_FAIL

goto RUN

:NO_GO
echo [agent02] No binary found. Auto-download failed and Go is not installed.
echo Install Go 1.25+ OR place agent02.exe in:
echo   - %BIN%
echo   - %ROOT_BIN%
echo Or publish release assets for repo: %REPO%
pause
exit /b 1

:BUILD_FAIL
echo [agent02] Build failed.
pause
exit /b 1

:RUN
echo [agent02] Starting Agent-02...
"%BIN%" start --data-dir "%DATA_DIR%"
set "RC=%errorlevel%"
if not "%RC%"=="0" (
  echo.
  echo [agent02] Agent-02 exited with code %RC%.
  pause
)
exit /b %RC%

:DOWNLOAD_PREBUILT
set "ASSET=agent02-windows-%ARCH%.zip"
set "BASE_URL=https://github.com/%REPO%/releases/latest/download"
set "ZIP_PATH=%TEMP%\%ASSET%"
set "SUM_PATH=%TEMP%\agent02-checksums.txt"
set "EXTRACT_DIR=%TEMP%\agent02-extract-%RANDOM%%RANDOM%"

echo [agent02] Trying prebuilt download: %ASSET%
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -Uri '%BASE_URL%/%ASSET%' -OutFile '%ZIP_PATH%' -UseBasicParsing; Invoke-WebRequest -Uri '%BASE_URL%/agent02-checksums.txt' -OutFile '%SUM_PATH%' -UseBasicParsing; exit 0 } catch { exit 1 }"
if %errorlevel% neq 0 (
  echo [agent02] Prebuilt download unavailable.
  exit /b 1
)

echo [agent02] Verifying checksum...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$sumLine=(Get-Content '%SUM_PATH%' | Where-Object { $_ -match ' %ASSET%$' } | Select-Object -First 1); if (-not $sumLine) { exit 1 }; $expected=($sumLine -split '\s+')[0].ToLower(); $actual=(Get-FileHash '%ZIP_PATH%' -Algorithm SHA256).Hash.ToLower(); if ($expected -ne $actual) { exit 1 } else { exit 0 }"
if %errorlevel% neq 0 (
  echo [agent02] Checksum verification failed.
  exit /b 1
)

echo [agent02] Extracting...
if exist "%EXTRACT_DIR%" rmdir /s /q "%EXTRACT_DIR%" >nul 2>nul
mkdir "%EXTRACT_DIR%" >nul 2>nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Force -Path '%ZIP_PATH%' -DestinationPath '%EXTRACT_DIR%'"
if %errorlevel% neq 0 exit /b 1

if exist "%EXTRACT_DIR%\agent02.exe" (
  copy /Y "%EXTRACT_DIR%\agent02.exe" "%BIN%" >nul
) else (
  exit /b 1
)

if exist "%ZIP_PATH%" del /q "%ZIP_PATH%" >nul 2>nul
if exist "%SUM_PATH%" del /q "%SUM_PATH%" >nul 2>nul
if exist "%EXTRACT_DIR%" rmdir /s /q "%EXTRACT_DIR%" >nul 2>nul

echo [agent02] Prebuilt binary ready at %BIN%
exit /b 0
