#Requires -Version 5.1
<#
.SYNOPSIS
    Agent-02 installer: mirror an OpenClaw source checkout, build it,
    and generate thin launchers for llama-server + OpenClaw gateway.

.DESCRIPTION
    This is the only supported install entrypoint for Agent-02.
    It reads user-owned config from install.local.bat, mirrors the
    OpenClaw source into .agent02-local/openclaw, builds it, and writes
    launcher/docs artifacts under .agent02-local/.

    Skills applied:
      - install-openclaw: upstream source path, gateway/dashboard flow,
        and provider-boundary rules
      - llama-knowledge: llama-server flags, /health, /v1/models, and
        Windows runtime behavior

.NOTES
    Install never starts services, never writes OpenClaw provider
    config, and never selects a default model for OpenClaw.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not ('Agent02.NativeMethods' -as [type])) {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

namespace Agent02 {
    public static class NativeMethods {
        [DllImport("shell32.dll", SetLastError = true)]
        public static extern IntPtr CommandLineToArgvW(
            [MarshalAs(UnmanagedType.LPWStr)] string lpCmdLine,
            out int pNumArgs
        );

        [DllImport("kernel32.dll")]
        public static extern IntPtr LocalFree(IntPtr hMem);
    }
}
"@
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RepoRoot = Split-Path -Parent $ScriptDir
$ConfigBat = Join-Path $RepoRoot 'install.local.bat'
$LocalRoot = Join-Path $RepoRoot '.agent02-local'
$MirrorDir = Join-Path $LocalRoot 'openclaw'
$LauncherDir = Join-Path $LocalRoot 'launcher'
$DocsDir = Join-Path $LocalRoot 'docs'
$BinDir = Join-Path $LocalRoot 'bin'

function Write-Step ([string]$Message) {
    Write-Host "[*] $Message" -ForegroundColor Cyan
}

function Write-Ok ([string]$Message) {
    Write-Host "[+] $Message" -ForegroundColor Green
}

function Write-Warn ([string]$Message) {
    Write-Host "[!] $Message" -ForegroundColor Yellow
}

function Write-Fail ([string]$Message) {
    Write-Host "[-] $Message" -ForegroundColor Red
}

function Exit-WithError ([string]$Message) {
    Write-Fail $Message
    exit 1
}

function Write-Utf8File ([string]$Path, [string]$Content) {
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    [System.IO.File]::WriteAllText($Path, $Content, [System.Text.UTF8Encoding]::new($false))
}

function Read-ConfigBat ([string]$Path) {
    if (-not (Test-Path $Path)) {
        Exit-WithError "Missing config file: $Path`nCopy install.local.bat.example to install.local.bat and fill in your paths."
    }

    $vars = @{}
    foreach ($line in Get-Content $Path) {
        if ($line -match '^\s*set\s+"([^=]+)=(.*)"\s*$') {
            $vars[$Matches[1]] = $Matches[2]
            continue
        }
        if ($line -match '^\s*set\s+([^=\s]+)=(.*)\s*$') {
            $vars[$Matches[1]] = $Matches[2]
        }
    }
    return $vars
}

function Get-ConfigValue ([hashtable]$Config, [string]$Name, [string]$Default = '') {
    if (-not $Config.ContainsKey($Name)) {
        return $Default
    }
    $value = $Config[$Name]
    if ($null -eq $value) {
        return $Default
    }
    return [string]$value
}

function Split-WindowsCommandLine ([string]$CommandLine) {
    if ([string]::IsNullOrWhiteSpace($CommandLine)) {
        return @()
    }

    $argc = 0
    $argvPtr = [Agent02.NativeMethods]::CommandLineToArgvW($CommandLine, [ref]$argc)
    if ($argvPtr -eq [IntPtr]::Zero) {
        throw "Could not parse command line: $CommandLine"
    }

    try {
        $args = New-Object string[] $argc
        for ($index = 0; $index -lt $argc; $index++) {
            $itemPtr = [System.Runtime.InteropServices.Marshal]::ReadIntPtr(
                $argvPtr,
                $index * [IntPtr]::Size
            )
            $args[$index] = [System.Runtime.InteropServices.Marshal]::PtrToStringUni($itemPtr)
        }
        return $args
    } finally {
        [void][Agent02.NativeMethods]::LocalFree($argvPtr)
    }
}

function Get-ReservedLlamaArgs ([string[]]$Args) {
    $reserved = @()
    foreach ($arg in $Args) {
        switch -Regex ($arg) {
            '^-m$' { $reserved += $arg; continue }
            '^--model$' { $reserved += $arg; continue }
            '^--host$' { $reserved += $arg; continue }
            '^--port$' { $reserved += $arg; continue }
            '^--api-key$' { $reserved += $arg; continue }
            '^--api-key-file$' { $reserved += $arg; continue }
            '^--host=' { $reserved += $arg; continue }
            '^--port=' { $reserved += $arg; continue }
            '^--api-key=' { $reserved += $arg; continue }
            '^--api-key-file=' { $reserved += $arg; continue }
        }
    }
    return $reserved
}

function Assert-ExtraLlamaArgs ([hashtable]$Config) {
    $extra = Get-ConfigValue $Config 'EXTRA_LLAMA_ARGS'
    if ([string]::IsNullOrWhiteSpace($extra)) {
        return
    }

    $parsed = Split-WindowsCommandLine $extra
    $reserved = Get-ReservedLlamaArgs $parsed
    if ($reserved.Count -gt 0) {
        Exit-WithError (
            "EXTRA_LLAMA_ARGS contains reserved llama-server flags: " +
            ($reserved -join ', ') +
            ". Do not override -m, --host, --port, --api-key, or --api-key-file."
        )
    }
}

function Invoke-ExternalProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [string[]]$ArgumentList = @(),

        [string]$WorkingDirectory = $RepoRoot
    )

    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory `
        -NoNewWindow `
        -Wait `
        -PassThru

    $global:LASTEXITCODE = $process.ExitCode
    return $process.ExitCode
}

$script:PnpmCmd = @()

function Invoke-Pnpm {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )

    if ($script:PnpmCmd.Count -eq 0) {
        throw 'pnpm command is not initialized.'
    }

    $filePath = $script:PnpmCmd[0]
    $fullArgs = @()
    if ($script:PnpmCmd.Count -gt 1) {
        $fullArgs += $script:PnpmCmd[1..($script:PnpmCmd.Count - 1)]
    }
    if ($Arguments) {
        $fullArgs += $Arguments
    }

    return Invoke-ExternalProcess -FilePath $filePath -ArgumentList $fullArgs -WorkingDirectory (Get-Location)
}

function Install-PnpmShim {
    if (-not (Test-Path $BinDir)) {
        New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
    }

    Write-Utf8File (Join-Path $BinDir 'pnpm.cmd') "@echo off`r`ncorepack pnpm %*`r`n"
    Write-Utf8File (Join-Path $BinDir 'pnpm') "#!/usr/bin/env bash`ncorepack pnpm ""`$@""`n"

    $processPath = [Environment]::GetEnvironmentVariable('PATH', 'Process')
    [Environment]::SetEnvironmentVariable('PATH', "$BinDir;$processPath", 'Process')
    $env:PATH = "$BinDir;$env:PATH"
    [Environment]::SetEnvironmentVariable('npm_execpath', (Join-Path $BinDir 'pnpm.cmd'), 'Process')

    Write-Ok 'Workspace-local pnpm shim installed in .agent02-local/bin/.'
}

function Assert-NodeVersion {
    Write-Step 'Checking Node.js >= 22 ...'
    $node = Get-Command node -ErrorAction SilentlyContinue
    if (-not $node) {
        Exit-WithError 'Node.js is not installed or not on PATH.'
    }

    $raw = (& node --version 2>&1 | Out-String).Trim()
    if ($raw -notmatch '^v(\d+)') {
        Exit-WithError "Could not parse Node.js version: $raw"
    }

    if ([int]$Matches[1] -lt 22) {
        Exit-WithError "Node.js $raw found, but Node.js >= 22 is required."
    }

    Write-Ok "Node.js $raw"
}

function Assert-Pnpm {
    Write-Step 'Checking pnpm ...'

    $direct = Get-Command pnpm -ErrorAction SilentlyContinue
    if ($direct) {
        $script:PnpmCmd = @('pnpm')
        $version = (& pnpm --version 2>&1 | Out-String).Trim()
        Write-Ok "pnpm $version"
        return
    }

    Write-Warn 'pnpm not found directly, trying corepack pnpm ...'
    $corepack = Get-Command corepack -ErrorAction SilentlyContinue
    if (-not $corepack) {
        Exit-WithError 'Neither pnpm nor corepack was found on PATH.'
    }

    try {
        $version = (& corepack pnpm --version 2>&1 | Out-String).Trim()
        if ($LASTEXITCODE -eq 0 -and $version -match '^\d+\.') {
            $script:PnpmCmd = @('corepack', 'pnpm')
            Write-Ok "pnpm $version (via corepack)"
            Install-PnpmShim
            return
        }
    } catch {
    }

    & corepack enable 2>&1 | Out-Null
    $directAfterEnable = Get-Command pnpm -ErrorAction SilentlyContinue
    if ($directAfterEnable) {
        $script:PnpmCmd = @('pnpm')
        $version = (& pnpm --version 2>&1 | Out-String).Trim()
        Write-Ok "pnpm $version (via corepack enable)"
        return
    }

    Exit-WithError 'Could not find or activate pnpm. Install pnpm or enable it with corepack.'
}

function Get-OpenClawPackage ([string]$SourceDir) {
    $packagePath = Join-Path $SourceDir 'package.json'
    if (-not (Test-Path $packagePath)) {
        Exit-WithError "No package.json was found in OPENCLAW_SOURCE_DIR: $SourceDir"
    }
    return Get-Content $packagePath -Raw | ConvertFrom-Json
}

function Assert-OpenClawSource ([string]$SourceDir) {
    Write-Step "Validating OpenClaw source checkout at: $SourceDir"
    if (-not (Test-Path $SourceDir)) {
        Exit-WithError "OPENCLAW_SOURCE_DIR does not exist: $SourceDir"
    }

    $package = Get-OpenClawPackage $SourceDir
    $hasOpenClawName = $package.name -and $package.name -match 'openclaw'
    $hasOpenClawScript = $package.scripts -and (
        $package.scripts.PSObject.Properties.Name -contains 'openclaw' -or
        (($package.scripts | ConvertTo-Json -Compress) -match 'openclaw')
    )

    if (-not ($hasOpenClawName -or $hasOpenClawScript)) {
        Exit-WithError "package.json in $SourceDir does not look like an OpenClaw checkout."
    }

    if (-not (Test-Path (Join-Path $SourceDir 'pnpm-workspace.yaml'))) {
        Write-Warn 'pnpm-workspace.yaml was not found. This may still work, but it does not look like the expected source checkout.'
    }

    Write-Ok "OpenClaw source validated: $SourceDir"
}

function Assert-LlamaServerExe ([string]$ExePath) {
    Write-Step "Validating llama-server.exe at: $ExePath"
    if (-not (Test-Path $ExePath)) {
        Exit-WithError "LLAMA_SERVER_EXE was not found: $ExePath"
    }

    if ([System.IO.Path]::GetExtension($ExePath).ToLowerInvariant() -ne '.exe') {
        Write-Warn 'LLAMA_SERVER_EXE does not have a .exe extension. Continuing because the file exists.'
    }

    Write-Ok "llama-server.exe found: $ExePath"
}

function Get-ReferencedPnpmScripts ([string]$Command) {
    $pattern = '(?<![\w-])pnpm(?:\s+run)?\s+([A-Za-z0-9:_-]+)'
    return [regex]::Matches($Command, $pattern) | ForEach-Object { $_.Groups[1].Value }
}

function Test-CommandNeedsBash ([string]$Command) {
    if ([string]::IsNullOrWhiteSpace($Command)) {
        return $false
    }

    if ($Command -match '(^|[;&|]\s*)(bash|sh)(\s|$)') {
        return $true
    }
    if ($Command -match '\.sh(\s|$)') {
        return $true
    }

    return $false
}

function Test-ScriptNeedsBash {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Scripts,

        [Parameter(Mandatory = $true)]
        [string]$ScriptName,

        [System.Collections.Generic.HashSet[string]]$Seen = $(New-Object 'System.Collections.Generic.HashSet[string]')
    )

    if (-not $Scripts.ContainsKey($ScriptName)) {
        return $false
    }

    if (-not $Seen.Add($ScriptName)) {
        return $false
    }

    $command = [string]$Scripts[$ScriptName]
    if (Test-CommandNeedsBash $command) {
        return $true
    }

    foreach ($nested in Get-ReferencedPnpmScripts $command) {
        if (Test-ScriptNeedsBash -Scripts $Scripts -ScriptName $nested -Seen $Seen) {
            return $true
        }
    }

    return $false
}

function Assert-BashIfNeeded ([string]$SourceDir) {
    $package = Get-OpenClawPackage $SourceDir
    $scripts = @{}
    if ($package.scripts) {
        foreach ($property in $package.scripts.PSObject.Properties) {
            $scripts[$property.Name] = [string]$property.Value
        }
    }

    $needsBash = Test-ScriptNeedsBash -Scripts $scripts -ScriptName 'build'
    if (-not $needsBash) {
        Write-Ok 'Current OpenClaw build chain does not require bash.'
        return
    }

    Write-Step 'OpenClaw build chain requires bash. Checking for a usable bash ...'

    $bash = Get-Command bash -ErrorAction SilentlyContinue
    $bashPath = if ($bash) { $bash.Source } else { '' }
    $looksLikeWslStub = $bashPath -and ($bashPath -match 'System32\\bash(\.exe)?$')

    if (-not $bash -or $looksLikeWslStub) {
        $git = Get-Command git -ErrorAction SilentlyContinue
        if ($git) {
            $gitRoot = Split-Path (Split-Path $git.Source -Parent) -Parent
            $gitBin = Join-Path $gitRoot 'bin'
            $gitBash = Join-Path $gitBin 'bash.exe'
            if (Test-Path $gitBash) {
                $processPath = [Environment]::GetEnvironmentVariable('PATH', 'Process')
                [Environment]::SetEnvironmentVariable('PATH', "$gitBin;$processPath", 'Process')
                $env:PATH = "$gitBin;$env:PATH"
                Write-Ok "Git Bash found and injected into PATH: $gitBash"
                return
            }
        }
    }

    if (-not $bash) {
        Exit-WithError 'A real bash is required for the current OpenClaw build chain. Install Git Bash and rerun the installer.'
    }
    if ($looksLikeWslStub) {
        Exit-WithError "bash resolves to the WSL stub ($bashPath). Install Git Bash so the current OpenClaw build can run on Windows."
    }

    Write-Ok "bash found: $bashPath"
}

function Sync-OpenClawSource ([string]$SourceDir, [string]$DestinationDir) {
    Write-Step "Mirroring OpenClaw source into $DestinationDir ..."

    if (-not (Test-Path $DestinationDir)) {
        New-Item -ItemType Directory -Path $DestinationDir -Force | Out-Null
    }

    $excludeDirs = @(
        '.git',
        'node_modules',
        'dist',
        '.openclaw',
        '.turbo',
        '.next',
        '.cache',
        '.artifacts',
        'coverage',
        'build',
        '.build',
        'tmp',
        'temp',
        '__pycache__'
    )
    $excludeFiles = @('*.log', '*.tmp', '*.temp', '*.bak', '*.pid')

    $robocopyArgs = @(
        $SourceDir,
        $DestinationDir,
        '/MIR',
        '/NFL',
        '/NDL',
        '/NJH',
        '/NJS',
        '/NC',
        '/NS',
        '/NP'
    )
    foreach ($dir in $excludeDirs) {
        $robocopyArgs += '/XD'
        $robocopyArgs += $dir
    }
    foreach ($file in $excludeFiles) {
        $robocopyArgs += '/XF'
        $robocopyArgs += $file
    }

    & robocopy @robocopyArgs | Out-Null
    if ($LASTEXITCODE -gt 7) {
        Exit-WithError "robocopy failed with exit code $LASTEXITCODE"
    }

    Write-Ok 'Source mirror complete.'
}

function Build-OpenClaw ([string]$WorkingDir) {
    Push-Location $WorkingDir
    try {
        Write-Step 'Running pnpm install ...'
        Invoke-Pnpm install
        if ($LASTEXITCODE -ne 0) {
            Exit-WithError 'pnpm install failed.'
        }
        Write-Ok 'pnpm install complete.'

        $userConfigPath = Join-Path $env:USERPROFILE '.openclaw\openclaw.json'
        if (-not (Test-Path $userConfigPath)) {
            Write-Step 'No user OpenClaw config found. Running pnpm openclaw setup ...'
            Invoke-Pnpm openclaw setup
            if ($LASTEXITCODE -ne 0) {
                Exit-WithError 'pnpm openclaw setup failed.'
            }
            Write-Ok 'pnpm openclaw setup complete.'
        } else {
            Write-Ok "User OpenClaw config already exists at $userConfigPath. Skipping pnpm openclaw setup."
        }

        Write-Step 'Running pnpm build ...'
        Invoke-Pnpm build
        if ($LASTEXITCODE -ne 0) {
            Exit-WithError 'pnpm build failed.'
        }
        Write-Ok 'pnpm build complete.'
    } finally {
        Pop-Location
    }
}

function New-Launchers ([string]$TargetDir) {
    Write-Step "Generating launchers in $TargetDir ..."
    if (-not (Test-Path $TargetDir)) {
        New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
    }

    $runBat = @'
@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_run-agent02.ps1" %*
'@

    $stopBat = @'
@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_stop-agent02.ps1"
'@

    $commonPs1 = @'
#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not ('Agent02.NativeMethods' -as [type])) {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

namespace Agent02 {
    public static class NativeMethods {
        [DllImport("shell32.dll", SetLastError = true)]
        public static extern IntPtr CommandLineToArgvW(
            [MarshalAs(UnmanagedType.LPWStr)] string lpCmdLine,
            out int pNumArgs
        );

        [DllImport("kernel32.dll")]
        public static extern IntPtr LocalFree(IntPtr hMem);
    }
}
"@
}

function Write-Agent02Info ([string]$Message) {
    Write-Host "[*] $Message" -ForegroundColor Cyan
}

function Write-Agent02Ok ([string]$Message) {
    Write-Host "[+] $Message" -ForegroundColor Green
}

function Write-Agent02Warn ([string]$Message) {
    Write-Host "[!] $Message" -ForegroundColor Yellow
}

function Write-Agent02Fail ([string]$Message) {
    Write-Host "[-] $Message" -ForegroundColor Red
}

function Get-Agent02Paths {
    $localRoot = Split-Path -Parent $PSScriptRoot
    $repoRoot = Split-Path -Parent $localRoot
    return @{
        RepoRoot = $repoRoot
        LocalRoot = $localRoot
        ConfigBat = Join-Path $repoRoot 'install.local.bat'
        OpenClawDir = Join-Path $localRoot 'openclaw'
        RuntimeDir = Join-Path $localRoot 'runtime'
        LauncherDir = $PSScriptRoot
        BinDir = Join-Path $localRoot 'bin'
    }
}

function Initialize-Agent02Path ([hashtable]$Paths) {
    if (Test-Path $Paths.BinDir) {
        $env:PATH = "$($Paths.BinDir);$env:PATH"
    }
}

function Read-Agent02Config ([string]$Path) {
    if (-not (Test-Path $Path)) {
        throw "Missing config file: $Path. Recreate install.local.bat from install.local.bat.example."
    }

    $vars = @{}
    foreach ($line in Get-Content $Path) {
        if ($line -match '^\s*set\s+"([^=]+)=(.*)"\s*$') {
            $vars[$Matches[1]] = $Matches[2]
            continue
        }
        if ($line -match '^\s*set\s+([^=\s]+)=(.*)\s*$') {
            $vars[$Matches[1]] = $Matches[2]
        }
    }
    return $vars
}

function Get-Agent02ConfigValue ([hashtable]$Config, [string]$Name, [string]$Default = '') {
    if (-not $Config.ContainsKey($Name)) {
        return $Default
    }
    $value = $Config[$Name]
    if ($null -eq $value) {
        return $Default
    }
    return [string]$value
}

function Split-Agent02CommandLine ([string]$CommandLine) {
    if ([string]::IsNullOrWhiteSpace($CommandLine)) {
        return @()
    }

    $argc = 0
    $argvPtr = [Agent02.NativeMethods]::CommandLineToArgvW($CommandLine, [ref]$argc)
    if ($argvPtr -eq [IntPtr]::Zero) {
        throw "Could not parse command line: $CommandLine"
    }

    try {
        $args = New-Object string[] $argc
        for ($index = 0; $index -lt $argc; $index++) {
            $itemPtr = [System.Runtime.InteropServices.Marshal]::ReadIntPtr(
                $argvPtr,
                $index * [IntPtr]::Size
            )
            $args[$index] = [System.Runtime.InteropServices.Marshal]::PtrToStringUni($itemPtr)
        }
        return $args
    } finally {
        [void][Agent02.NativeMethods]::LocalFree($argvPtr)
    }
}

function Get-Agent02ReservedLlamaArgs ([string[]]$Args) {
    $reserved = @()
    foreach ($arg in $Args) {
        switch -Regex ($arg) {
            '^-m$' { $reserved += $arg; continue }
            '^--model$' { $reserved += $arg; continue }
            '^--host$' { $reserved += $arg; continue }
            '^--port$' { $reserved += $arg; continue }
            '^--api-key$' { $reserved += $arg; continue }
            '^--api-key-file$' { $reserved += $arg; continue }
            '^--host=' { $reserved += $arg; continue }
            '^--port=' { $reserved += $arg; continue }
            '^--api-key=' { $reserved += $arg; continue }
            '^--api-key-file=' { $reserved += $arg; continue }
        }
    }
    return $reserved
}

function Resolve-Agent02Port ([string]$RawValue, [int]$DefaultPort) {
    $trimmed = if ($null -eq $RawValue) { '' } else { [string]$RawValue }
    $trimmed = $trimmed.Trim()
    if ($trimmed -eq '') {
        return $DefaultPort
    }

    $parsed = 0
    if (-not [int]::TryParse($trimmed, [ref]$parsed) -or $parsed -le 0) {
        throw "Invalid port value: $RawValue"
    }
    return $parsed
}

function Resolve-Agent02NoOpen ([string]$RawValue) {
    $trimmed = if ($null -eq $RawValue) { '' } else { [string]$RawValue }
    $trimmed = $trimmed.Trim().ToLowerInvariant()
    if ($trimmed -eq '' -or $trimmed -eq '0' -or $trimmed -eq 'false') {
        return $false
    }
    if ($trimmed -eq '1' -or $trimmed -eq 'true') {
        return $true
    }
    throw "Invalid OPENCLAW_NO_OPEN value: $RawValue (expected 0 or 1)"
}

function Ensure-Agent02RuntimeDir ([string]$RuntimeDir) {
    if (-not (Test-Path $RuntimeDir)) {
        New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null
    }
}

function Get-Agent02ManifestPath ([string]$RuntimeDir, [string]$Name) {
    return Join-Path $RuntimeDir "$Name.json"
}

function Get-Agent02PidPath ([string]$RuntimeDir, [string]$Name) {
    return Join-Path $RuntimeDir "$Name.pid"
}

function Remove-Agent02Tracking ([string]$RuntimeDir, [string]$Name) {
    Remove-Item (Get-Agent02ManifestPath $RuntimeDir $Name) -Force -ErrorAction SilentlyContinue
    Remove-Item (Get-Agent02PidPath $RuntimeDir $Name) -Force -ErrorAction SilentlyContinue
}

function Get-Agent02ProcessRecord ([int]$TargetProcessId) {
    return Get-CimInstance Win32_Process -Filter "ProcessId = $TargetProcessId" -ErrorAction SilentlyContinue
}

function Get-Agent02Tracking ([string]$RuntimeDir, [string]$Name) {
    $manifestPath = Get-Agent02ManifestPath $RuntimeDir $Name
    if (Test-Path $manifestPath) {
        try {
            return Get-Content $manifestPath -Raw | ConvertFrom-Json
        } catch {
            Remove-Agent02Tracking $RuntimeDir $Name
            return $null
        }
    }

    $pidPath = Get-Agent02PidPath $RuntimeDir $Name
    if (Test-Path $pidPath) {
        $rawPid = (Get-Content $pidPath -Raw).Trim()
        if ($rawPid -match '^\d+$') {
            return [pscustomobject]@{
                pid = [int]$rawPid
                creationDate = $null
                stdoutLog = $null
                stderrLog = $null
            }
        }
        Remove-Agent02Tracking $RuntimeDir $Name
    }

    return $null
}

function Test-Agent02TrackedProcessAlive ([string]$RuntimeDir, [string]$Name) {
    $tracking = Get-Agent02Tracking $RuntimeDir $Name
    if (-not $tracking) {
        return $false
    }

    $record = Get-Agent02ProcessRecord ([int]$tracking.pid)
    if (-not $record) {
        Remove-Agent02Tracking $RuntimeDir $Name
        return $false
    }

    if ($tracking.creationDate) {
        if ([string]$record.CreationDate -ne [string]$tracking.creationDate) {
            Remove-Agent02Tracking $RuntimeDir $Name
            return $false
        }
    }

    return $true
}

function Assert-Agent02NoTrackedProcess ([string]$RuntimeDir, [string]$Name, [string]$Label) {
    if (Get-Agent02LiveTracking -RuntimeDir $RuntimeDir -Name $Name -AllowRecovery) {
        throw "$Label is already running. Stop it with stop-agent02.bat before launching again."
    }
}

function Save-Agent02Tracking {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RuntimeDir,
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [System.Diagnostics.Process]$Process,
        [Parameter(Mandatory = $true)]
        [string]$Label,
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,
        [Parameter(Mandatory = $true)]
        [string]$StdOutLog,
        [Parameter(Mandatory = $true)]
        [string]$StdErrLog
    )

    Start-Sleep -Milliseconds 200
    $record = Get-Agent02ProcessRecord $Process.Id
    if (-not $record) {
        throw "$Label exited before it could be tracked."
    }

    $manifest = [ordered]@{
        label = $Label
        pid = $Process.Id
        creationDate = [string]$record.CreationDate
        executablePath = [string]$record.ExecutablePath
        commandLine = [string]$record.CommandLine
        workingDirectory = $WorkingDirectory
        command = $Command
        stdoutLog = $StdOutLog
        stderrLog = $StdErrLog
    }

    Set-Content -Path (Get-Agent02PidPath $RuntimeDir $Name) -Value $Process.Id -Encoding ASCII
    [System.IO.File]::WriteAllText(
        (Get-Agent02ManifestPath $RuntimeDir $Name),
        ($manifest | ConvertTo-Json -Depth 5),
        [System.Text.UTF8Encoding]::new($false)
    )

    return [pscustomobject]$manifest
}

function Start-Agent02Process {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RuntimeDir,
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Label,
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [string[]]$ArgumentList = @(),
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,
        [Parameter(Mandatory = $true)]
        [string]$StdOutLog,
        [Parameter(Mandatory = $true)]
        [string]$StdErrLog,
        [Parameter(Mandatory = $true)]
        [string]$Command
    )

    Assert-Agent02NoTrackedProcess $RuntimeDir $Name $Label

    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput $StdOutLog `
        -RedirectStandardError $StdErrLog `
        -PassThru

    Start-Sleep -Milliseconds 300
    if ($process.HasExited) {
        throw "$Label exited immediately. See logs: $StdOutLog and $StdErrLog"
    }

    return Save-Agent02Tracking `
        -RuntimeDir $RuntimeDir `
        -Name $Name `
        -Process $process `
        -Label $Label `
        -Command $Command `
        -WorkingDirectory $WorkingDirectory `
        -StdOutLog $StdOutLog `
        -StdErrLog $StdErrLog
}

function Stop-Agent02TrackedProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RuntimeDir,
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Label,
        [switch]$Quiet
    )

    $liveTracking = Get-Agent02LiveTracking -RuntimeDir $RuntimeDir -Name $Name -AllowRecovery
    if (-not $liveTracking) {
        if (-not $Quiet) {
            Write-Agent02Info "No tracked or recoverable $Label process was found."
        }
        return $true
    }

    $tracking = $liveTracking.Tracking
    if ($liveTracking.Source -eq 'recovered' -and -not $Quiet) {
        Write-Agent02Warn "Recovered an untracked $Label process (PID $($tracking.pid))."
    }

    if (-not $Quiet) {
        Write-Agent02Info "Stopping $Label (PID $($tracking.pid)) ..."
    }

    $taskkillOutput = & taskkill /PID $tracking.pid /T /F 2>&1
    $taskkillExitCode = $LASTEXITCODE
    if ($taskkillExitCode -ne 0 -and -not $Quiet) {
        Write-Agent02Warn ($taskkillOutput | Out-String).Trim()
    }

    $record = $null
    $deadline = (Get-Date).AddSeconds(8)
    do {
        $record = Get-Agent02ProcessRecord ([int]$tracking.pid)
        if ($record -and $tracking.creationDate) {
            if ([string]$record.CreationDate -ne [string]$tracking.creationDate) {
                $record = $null
            }
        }

        if (-not $record) {
            break
        }

        Start-Sleep -Milliseconds 300
    } while ((Get-Date) -lt $deadline)

    if ($record) {
        if (-not $Quiet) {
            Write-Agent02Fail "$Label is still running after taskkill."
        }
        return $false
    }

    Remove-Agent02Tracking $RuntimeDir $Name

    if (-not $Quiet) {
        Write-Agent02Ok "$Label stopped."
    }

    return $true
}

function Wait-Agent02Health {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [Parameter(Mandatory = $true)]
        [int]$TimeoutSeconds,
        [Parameter(Mandatory = $true)]
        [scriptblock]$AliveCheck
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (-not (& $AliveCheck)) {
            return $false
        }

        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
                return $true
            }
        } catch {
        }

        Start-Sleep -Seconds 2
    }

    return $false
}

function Wait-Agent02PortOpen {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TargetHost,
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [int]$TimeoutSeconds,
        [Parameter(Mandatory = $true)]
        [scriptblock]$AliveCheck
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (-not (& $AliveCheck)) {
            return $false
        }

        $client = New-Object System.Net.Sockets.TcpClient
        try {
            $async = $client.BeginConnect($TargetHost, $Port, $null, $null)
            if ($async.AsyncWaitHandle.WaitOne(1000, $false) -and $client.Connected) {
                $client.EndConnect($async) | Out-Null
                return $true
            }
        } catch {
        } finally {
            $client.Dispose()
        }

        Start-Sleep -Seconds 2
    }

    return $false
}

function Invoke-Agent02DashboardCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$OpenClawDir,
        [Parameter(Mandatory = $true)]
        [bool]$NoOpen
    )

    $command = if ($NoOpen) {
        'pnpm openclaw dashboard --no-open'
    } else {
        'pnpm openclaw dashboard'
    }

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = 'cmd.exe'
    $startInfo.Arguments = "/d /c $command"
    $startInfo.WorkingDirectory = $OpenClawDir
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true

    $process = [System.Diagnostics.Process]::Start($startInfo)
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()

    $dashboardUrl = $null
    $combined = ($stdout + [Environment]::NewLine + $stderr)
    if ($combined -match 'Dashboard URL:\s*(\S+)') {
        $dashboardUrl = $Matches[1]
    }

    return [pscustomobject]@{
        ExitCode = $process.ExitCode
        DashboardUrl = $dashboardUrl
        StdOut = $stdout.Trim()
        StdErr = $stderr.Trim()
        Command = $command
    }
}
'@

    $runPs1 = @'
#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot '_agent02-common.ps1')

$paths = Get-Agent02Paths
Initialize-Agent02Path $paths
$runtimeDir = $paths.RuntimeDir
$openClawDir = $paths.OpenClawDir
$started = New-Object System.Collections.Generic.List[string]
$launcherArgs = @($args)

function Cleanup-Agent02OnFailure {
    for ($index = $started.Count - 1; $index -ge 0; $index--) {
        switch ($started[$index]) {
            'openclaw-gateway' { Stop-Agent02TrackedProcess -RuntimeDir $runtimeDir -Name 'openclaw-gateway' -Label 'OpenClaw gateway' -Quiet }
            'llama-server' { Stop-Agent02TrackedProcess -RuntimeDir $runtimeDir -Name 'llama-server' -Label 'llama-server' -Quiet }
        }
    }
}

try {
    if (-not (Test-Path $openClawDir)) {
        throw "OpenClaw mirror was not found at $openClawDir. Run scripts/install-openclaw.ps1 first."
    }

    $config = Read-Agent02Config $paths.ConfigBat

    $llamaExe = Get-Agent02ConfigValue $config 'LLAMA_SERVER_EXE'
    if ([string]::IsNullOrWhiteSpace($llamaExe)) {
        throw 'LLAMA_SERVER_EXE is not set in install.local.bat.'
    }
    if (-not (Test-Path $llamaExe)) {
        throw "LLAMA_SERVER_EXE was not found: $llamaExe"
    }

    $apiKey = Get-Agent02ConfigValue $config 'LLAMA_SERVER_API_KEY' 'agent02-local'
    if ([string]::IsNullOrWhiteSpace($apiKey)) {
        $apiKey = 'agent02-local'
    }

    $openClawPort = Resolve-Agent02Port (Get-Agent02ConfigValue $config 'OPENCLAW_PORT') 18789
    $noOpen = Resolve-Agent02NoOpen (Get-Agent02ConfigValue $config 'OPENCLAW_NO_OPEN' '0')
    $extraArgs = @(Split-Agent02CommandLine (Get-Agent02ConfigValue $config 'EXTRA_LLAMA_ARGS'))
    $reservedArgs = @(Get-Agent02ReservedLlamaArgs $extraArgs)
    if ($reservedArgs.Count -gt 0) {
        throw (
            "EXTRA_LLAMA_ARGS contains reserved flags: " +
            ($reservedArgs -join ', ') +
            ". Do not override -m, --host, --port, --api-key, or --api-key-file."
        )
    }

    $modelPath = if ($launcherArgs.Count -gt 0 -and -not [string]::IsNullOrWhiteSpace($launcherArgs[0])) {
        $launcherArgs[0]
    } else {
        Get-Agent02ConfigValue $config 'MODEL_PATH'
    }

    if ([string]::IsNullOrWhiteSpace($modelPath)) {
        $modelPath = Read-Host 'Enter the path to a .gguf model file'
    }
    if ([string]::IsNullOrWhiteSpace($modelPath)) {
        throw 'No model path was provided.'
    }
    if (-not (Test-Path $modelPath)) {
        throw "Model file was not found: $modelPath"
    }
    if ([System.IO.Path]::GetExtension($modelPath).ToLowerInvariant() -ne '.gguf') {
        Write-Agent02Warn "The selected model does not end with .gguf: $modelPath"
    }

    Ensure-Agent02RuntimeDir $runtimeDir
    Assert-Agent02NoTrackedProcess $runtimeDir 'llama-server' 'llama-server'
    Assert-Agent02NoTrackedProcess $runtimeDir 'openclaw-gateway' 'OpenClaw gateway'

    $llamaStdOut = Join-Path $runtimeDir 'llama-server.stdout.log'
    $llamaStdErr = Join-Path $runtimeDir 'llama-server.stderr.log'
    $gatewayStdOut = Join-Path $runtimeDir 'openclaw-gateway.stdout.log'
    $gatewayStdErr = Join-Path $runtimeDir 'openclaw-gateway.stderr.log'

    $llamaArgs = @(
        '-m', $modelPath,
        '--host', '127.0.0.1',
        '--port', '8420',
        '--api-key', $apiKey
    ) + $extraArgs

    Write-Agent02Info 'Starting llama-server ...'
    $null = Start-Agent02Process `
        -RuntimeDir $runtimeDir `
        -Name 'llama-server' `
        -Label 'llama-server' `
        -FilePath $llamaExe `
        -ArgumentList $llamaArgs `
        -WorkingDirectory (Split-Path -Parent $llamaExe) `
        -StdOutLog $llamaStdOut `
        -StdErrLog $llamaStdErr `
        -Command (($llamaArgs | ForEach-Object {
            if ($_ -match '\s') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
        }) -join ' ')
    $started.Add('llama-server') | Out-Null

    Write-Agent02Info 'Waiting for llama-server /health ...'
    $healthReady = Wait-Agent02Health `
        -Url 'http://127.0.0.1:8420/health' `
        -TimeoutSeconds 120 `
        -AliveCheck { Test-Agent02TrackedProcessAlive $runtimeDir 'llama-server' }
    if (-not $healthReady) {
        throw "llama-server did not become healthy within 120 seconds. See logs: $llamaStdOut and $llamaStdErr"
    }
    Write-Agent02Ok 'llama-server is healthy.'

    Write-Agent02Info 'Querying authenticated /v1/models ...'
    $headers = @{ Authorization = "Bearer $apiKey" }
    try {
        $modelsResponse = Invoke-RestMethod -Uri 'http://127.0.0.1:8420/v1/models' -Headers $headers -TimeoutSec 10 -ErrorAction Stop
    } catch {
        throw "GET /v1/models failed. See logs: $llamaStdOut and $llamaStdErr"
    }

    $modelIds = @()
    if ($modelsResponse.data) {
        $modelIds = @($modelsResponse.data | ForEach-Object { [string]$_.id } | Where-Object { $_ })
    }
    if ($modelIds.Count -eq 0) {
        throw "GET /v1/models returned no model ids. See logs: $llamaStdOut and $llamaStdErr"
    }
    Write-Agent02Ok ("Model id(s): " + ($modelIds -join ', '))

    Write-Agent02Info 'Starting OpenClaw gateway ...'
    $gatewayCommand = "pnpm openclaw gateway --port $openClawPort --bind loopback"
    $null = Start-Agent02Process `
        -RuntimeDir $runtimeDir `
        -Name 'openclaw-gateway' `
        -Label 'OpenClaw gateway' `
        -FilePath 'cmd.exe' `
        -ArgumentList @('/d', '/c', $gatewayCommand) `
        -WorkingDirectory $openClawDir `
        -StdOutLog $gatewayStdOut `
        -StdErrLog $gatewayStdErr `
        -Command $gatewayCommand
    $started.Add('openclaw-gateway') | Out-Null

    $gatewayReady = Wait-Agent02PortOpen `
        -TargetHost '127.0.0.1' `
        -Port $openClawPort `
        -TimeoutSeconds 120 `
        -AliveCheck { Test-Agent02TrackedProcessAlive $runtimeDir 'openclaw-gateway' }
    if (-not $gatewayReady) {
        throw "OpenClaw gateway did not start on port $openClawPort. See logs: $gatewayStdOut and $gatewayStdErr"
    }
    Write-Agent02Ok "OpenClaw gateway is listening on port $openClawPort."

    $dashboardResult = Invoke-Agent02DashboardCommand -OpenClawDir $openClawDir -NoOpen $noOpen
    $dashboardUrl = if ($dashboardResult.DashboardUrl) {
        $dashboardResult.DashboardUrl
    } else {
        "http://127.0.0.1:$openClawPort/"
    }

    if ($dashboardResult.ExitCode -ne 0) {
        Write-Agent02Warn "openclaw dashboard did not complete cleanly. Falling back to $dashboardUrl"
        if ($dashboardResult.StdErr) {
            Write-Agent02Warn $dashboardResult.StdErr
        }
    } elseif ($dashboardResult.StdOut) {
        Write-Agent02Info $dashboardResult.StdOut
    }

    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Cyan
    Write-Host '  Agent-02 is running' -ForegroundColor Green
    Write-Host '============================================================' -ForegroundColor Cyan
    Write-Host ''
    Write-Host "  llama-server base URL : http://127.0.0.1:8420/v1" -ForegroundColor White
    Write-Host "  llama-server API key  : $apiKey" -ForegroundColor White
    Write-Host "  Model id(s)           : $($modelIds -join ', ')" -ForegroundColor White
    Write-Host "  OpenClaw dashboard    : $dashboardUrl" -ForegroundColor White
    Write-Host ''
    Write-Host "  llama-server logs     : $llamaStdOut | $llamaStdErr" -ForegroundColor DarkGray
    Write-Host "  gateway logs          : $gatewayStdOut | $gatewayStdErr" -ForegroundColor DarkGray
    Write-Host ''
    Write-Host 'Use the values above to configure the self-hosted provider inside OpenClaw.' -ForegroundColor Yellow
    Write-Host 'This launcher does not write provider config, pick a default model, or edit OpenClaw state.' -ForegroundColor Yellow
    Write-Host ''
    Write-Host 'Stop services with: stop-agent02.bat' -ForegroundColor DarkGray
    Write-Host ''
} catch {
    Write-Agent02Fail $_.Exception.Message
    Cleanup-Agent02OnFailure
    exit 1
}
'@

    $stopPs1 = @'
#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot '_agent02-common.ps1')

$paths = Get-Agent02Paths
$runtimeDir = $paths.RuntimeDir

$gatewayStopped = Stop-Agent02TrackedProcess -RuntimeDir $runtimeDir -Name 'openclaw-gateway' -Label 'OpenClaw gateway'
$llamaStopped = Stop-Agent02TrackedProcess -RuntimeDir $runtimeDir -Name 'llama-server' -Label 'llama-server'

if (-not $gatewayStopped -or -not $llamaStopped) {
    Write-Agent02Fail 'Agent-02 did not stop cleanly.'
    exit 1
}

Write-Agent02Ok 'Agent-02 stopped.'
'@

    Write-Utf8File (Join-Path $TargetDir 'run-agent02.bat') $runBat
    Write-Utf8File (Join-Path $TargetDir 'stop-agent02.bat') $stopBat
    Write-Utf8File (Join-Path $TargetDir '_agent02-common.ps1') $commonPs1
    Write-Utf8File (Join-Path $TargetDir '_run-agent02.ps1') $runPs1
    Write-Utf8File (Join-Path $TargetDir '_stop-agent02.ps1') $stopPs1

    Write-Ok 'Launchers generated.'
}

function New-LocalDocs ([string]$TargetDir) {
    Write-Step "Generating local usage docs in $TargetDir ..."
    if (-not (Test-Path $TargetDir)) {
        New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
    }

    $usageEn = @'
# Agent-02 Usage

Generated by `scripts/install-openclaw.ps1`.

## Runtime config

The generated launchers read `install.local.bat` every time they run.
You can change `MODEL_PATH`, `LLAMA_SERVER_API_KEY`, `OPENCLAW_PORT`,
`OPENCLAW_NO_OPEN`, or `EXTRA_LLAMA_ARGS` without regenerating the
launcher files.

## Starting

Run the launcher from `.agent02-local/launcher/`:

```bat
run-agent02.bat D:\Models\your-model.gguf
```

Model path resolution:

1. The first argument to `run-agent02.bat`
2. `MODEL_PATH` from `install.local.bat`
3. An interactive prompt if neither exists

## What the launcher does

1. Starts `llama-server.exe -m <gguf> --host 127.0.0.1 --port 8420 --api-key <key> ...`
2. Waits for public `GET /health`
3. Calls authenticated `GET http://127.0.0.1:8420/v1/models`
4. Starts `pnpm openclaw gateway --port <OPENCLAW_PORT> --bind loopback`
5. Runs the upstream `openclaw dashboard` flow to print or open the dashboard URL
6. Prints the base URL, API key, model id(s), dashboard URL, and log paths

## Manual provider setup in OpenClaw

Use the printed values:

| Field | Value |
| --- | --- |
| Base URL | `http://127.0.0.1:8420/v1` |
| API key | the configured `LLAMA_SERVER_API_KEY` |
| Model id | the id(s) returned by `/v1/models` |

This repo never writes provider config on your behalf.

## Runtime files

Runtime artifacts are created lazily under `.agent02-local/runtime/`:

- `llama-server.pid`
- `openclaw-gateway.pid`
- `llama-server.stdout.log`
- `llama-server.stderr.log`
- `openclaw-gateway.stdout.log`
- `openclaw-gateway.stderr.log`

## Stopping

Run:

```bat
stop-agent02.bat
```

It stops the tracked processes rooted at `.agent02-local/runtime/`.
If the PID/metadata files are missing, it can recover the current
launcher-owned `llama-server` or gateway process from the configured
port and command line before stopping it.
'@

    $usageVi = @'
# Huong dan su dung Agent-02

Duoc tao boi `scripts/install-openclaw.ps1`.

## Cau hinh runtime

Launcher duoc tao se doc lai `install.local.bat` moi lan chay.
Ban co the thay doi `MODEL_PATH`, `LLAMA_SERVER_API_KEY`,
`OPENCLAW_PORT`, `OPENCLAW_NO_OPEN`, hoac `EXTRA_LLAMA_ARGS`
ma khong can cai dat lai.

## Khoi dong

Chay launcher tu `.agent02-local/launcher/`:

```bat
run-agent02.bat D:\Models\your-model.gguf
```

Thu tu tim model path:

1. Tham so dau tien cua `run-agent02.bat`
2. `MODEL_PATH` trong `install.local.bat`
3. Hoi nguoi dung neu ca hai deu khong co

## Launcher lam gi

1. Khoi dong `llama-server.exe -m <gguf> --host 127.0.0.1 --port 8420 --api-key <key> ...`
2. Cho `GET /health`
3. Goi `GET http://127.0.0.1:8420/v1/models` co xac thuc
4. Khoi dong `pnpm openclaw gateway --port <OPENCLAW_PORT> --bind loopback`
5. Dung flow `openclaw dashboard` de in hoac mo dashboard URL
6. In ra base URL, API key, model id, dashboard URL, va duong dan log

## Thiet lap provider thu cong trong OpenClaw

Dung cac gia tri duoc in ra:

| Truong | Gia tri |
| --- | --- |
| Base URL | `http://127.0.0.1:8420/v1` |
| API key | `LLAMA_SERVER_API_KEY` da cau hinh |
| Model id | id duoc tra ve boi `/v1/models` |

Repo nay khong bao gio ghi provider config thay ban.

## Tep runtime

Tep runtime duoc tao lazy duoi `.agent02-local/runtime/`:

- `llama-server.pid`
- `openclaw-gateway.pid`
- `llama-server.stdout.log`
- `llama-server.stderr.log`
- `openclaw-gateway.stdout.log`
- `openclaw-gateway.stderr.log`

## Dung

```bat
stop-agent02.bat
```

Lenh nay se tat cac process dang duoc theo doi duoi
`.agent02-local/runtime/`.
Neu tep PID/metadata bi mat, launcher van co the tim lai
`llama-server` hoac gateway hien tai dua tren port cau hinh va
command line roi moi tat no.
'@

    Write-Utf8File (Join-Path $TargetDir 'usage.en.md') $usageEn
    Write-Utf8File (Join-Path $TargetDir 'usage.vi.md') $usageVi

    Write-Ok 'Local usage docs generated.'
}

Write-Host ''
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host '  Agent-02 Installer' -ForegroundColor Green
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host ''

Write-Step "Reading config from $ConfigBat ..."
$config = Read-ConfigBat $ConfigBat

$openClawSource = Get-ConfigValue $config 'OPENCLAW_SOURCE_DIR'
$llamaServerExe = Get-ConfigValue $config 'LLAMA_SERVER_EXE'

if ([string]::IsNullOrWhiteSpace($openClawSource)) {
    Exit-WithError 'OPENCLAW_SOURCE_DIR is not set in install.local.bat.'
}
if ([string]::IsNullOrWhiteSpace($llamaServerExe)) {
    Exit-WithError 'LLAMA_SERVER_EXE is not set in install.local.bat.'
}

Write-Ok "OPENCLAW_SOURCE_DIR = $openClawSource"
Write-Ok "LLAMA_SERVER_EXE    = $llamaServerExe"

Assert-ExtraLlamaArgs $config
Assert-NodeVersion
Assert-Pnpm
Assert-OpenClawSource $openClawSource
Assert-LlamaServerExe $llamaServerExe
Assert-BashIfNeeded $openClawSource

Sync-OpenClawSource $openClawSource $MirrorDir
Build-OpenClaw $MirrorDir
New-Launchers $LauncherDir
New-LocalDocs $DocsDir

Write-Host ''
Write-Host '============================================================' -ForegroundColor Green
Write-Host '  Install complete' -ForegroundColor Green
Write-Host '============================================================' -ForegroundColor Green
Write-Host ''
Write-Host "  Mirror:     $MirrorDir" -ForegroundColor White
Write-Host "  Launchers:  $LauncherDir" -ForegroundColor White
Write-Host "  Local docs: $DocsDir" -ForegroundColor White
Write-Host ''
Write-Host '  Next steps:' -ForegroundColor Yellow
Write-Host '    1. Run .agent02-local\launcher\run-agent02.bat <path-to-model.gguf>' -ForegroundColor White
Write-Host '    2. Use the printed values to configure the self-hosted provider inside OpenClaw' -ForegroundColor White
Write-Host ''

<#
    $stopBat = @'
@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_stop-agent02.ps1"
'@

    $commonPs1 = @'
#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not ('Agent02.NativeMethods' -as [type])) {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

namespace Agent02 {
    public static class NativeMethods {
        [DllImport("shell32.dll", SetLastError = true)]
        public static extern IntPtr CommandLineToArgvW(
            [MarshalAs(UnmanagedType.LPWStr)] string lpCmdLine,
            out int pNumArgs
        );

        [DllImport("kernel32.dll")]
        public static extern IntPtr LocalFree(IntPtr hMem);
    }
}
"@
}

function Write-Agent02Info ([string]$Message) {
    Write-Host "[*] $Message" -ForegroundColor Cyan
}

function Write-Agent02Ok ([string]$Message) {
    Write-Host "[+] $Message" -ForegroundColor Green
}

function Write-Agent02Warn ([string]$Message) {
    Write-Host "[!] $Message" -ForegroundColor Yellow
}

function Write-Agent02Fail ([string]$Message) {
    Write-Host "[-] $Message" -ForegroundColor Red
}

function Get-Agent02Paths {
    $localRoot = Split-Path -Parent $PSScriptRoot
    $repoRoot = Split-Path -Parent $localRoot
    return @{
        RepoRoot = $repoRoot
        LocalRoot = $localRoot
        ConfigBat = Join-Path $repoRoot 'install.local.bat'
        OpenClawDir = Join-Path $localRoot 'openclaw'
        RuntimeDir = Join-Path $localRoot 'runtime'
        LauncherDir = $PSScriptRoot
        BinDir = Join-Path $localRoot 'bin'
    }
}

function Initialize-Agent02Path ([hashtable]$Paths) {
    if (Test-Path $Paths.BinDir) {
        $env:PATH = "$($Paths.BinDir);$env:PATH"
    }
}

function Read-Agent02Config ([string]$Path) {
    if (-not (Test-Path $Path)) {
        throw "Missing config file: $Path. Recreate install.local.bat from install.local.bat.example."
    }

    $vars = @{}
    foreach ($line in Get-Content $Path) {
        if ($line -match '^\s*set\s+"([^=]+)=(.*)"\s*$') {
            $vars[$Matches[1]] = $Matches[2]
            continue
        }
        if ($line -match '^\s*set\s+([^=\s]+)=(.*)\s*$') {
            $vars[$Matches[1]] = $Matches[2]
        }
    }
    return $vars
}

function Get-Agent02ConfigValue ([hashtable]$Config, [string]$Name, [string]$Default = '') {
    if (-not $Config.ContainsKey($Name)) {
        return $Default
    }
    $value = $Config[$Name]
    if ($null -eq $value) {
        return $Default
    }
    return [string]$value
}

function Split-Agent02CommandLine ([string]$CommandLine) {
    if ([string]::IsNullOrWhiteSpace($CommandLine)) {
        return @()
    }

    $argc = 0
    $argvPtr = [Agent02.NativeMethods]::CommandLineToArgvW($CommandLine, [ref]$argc)
    if ($argvPtr -eq [IntPtr]::Zero) {
        throw "Could not parse command line: $CommandLine"
    }

    try {
        $args = New-Object string[] $argc
        for ($index = 0; $index -lt $argc; $index++) {
            $itemPtr = [System.Runtime.InteropServices.Marshal]::ReadIntPtr(
                $argvPtr,
                $index * [IntPtr]::Size
            )
            $args[$index] = [System.Runtime.InteropServices.Marshal]::PtrToStringUni($itemPtr)
        }
        return $args
    } finally {
        [void][Agent02.NativeMethods]::LocalFree($argvPtr)
    }
}

function Get-Agent02ReservedLlamaArgs ([string[]]$Args) {
    $reserved = @()
    foreach ($arg in $Args) {
        switch -Regex ($arg) {
            '^-m$' { $reserved += $arg; continue }
            '^--model$' { $reserved += $arg; continue }
            '^--host$' { $reserved += $arg; continue }
            '^--port$' { $reserved += $arg; continue }
            '^--api-key$' { $reserved += $arg; continue }
            '^--api-key-file$' { $reserved += $arg; continue }
            '^--host=' { $reserved += $arg; continue }
            '^--port=' { $reserved += $arg; continue }
            '^--api-key=' { $reserved += $arg; continue }
            '^--api-key-file=' { $reserved += $arg; continue }
        }
    }
    return $reserved
}

function Resolve-Agent02Port ([string]$RawValue, [int]$DefaultPort) {
    $trimmed = ($RawValue ?? '').Trim()
    if ($trimmed -eq '') {
        return $DefaultPort
    }

    $parsed = 0
    if (-not [int]::TryParse($trimmed, [ref]$parsed) -or $parsed -le 0) {
        throw "Invalid port value: $RawValue"
    }
    return $parsed
}

function Resolve-Agent02NoOpen ([string]$RawValue) {
    $trimmed = ($RawValue ?? '').Trim().ToLowerInvariant()
    if ($trimmed -eq '' -or $trimmed -eq '0' -or $trimmed -eq 'false') {
        return $false
    }
    if ($trimmed -eq '1' -or $trimmed -eq 'true') {
        return $true
    }
    throw "Invalid OPENCLAW_NO_OPEN value: $RawValue (expected 0 or 1)"
}

function Ensure-Agent02RuntimeDir ([string]$RuntimeDir) {
    if (-not (Test-Path $RuntimeDir)) {
        New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null
    }
}

function Get-Agent02ManifestPath ([string]$RuntimeDir, [string]$Name) {
    return Join-Path $RuntimeDir "$Name.json"
}

function Get-Agent02PidPath ([string]$RuntimeDir, [string]$Name) {
    return Join-Path $RuntimeDir "$Name.pid"
}

function Remove-Agent02Tracking ([string]$RuntimeDir, [string]$Name) {
    Remove-Item (Get-Agent02ManifestPath $RuntimeDir $Name) -Force -ErrorAction SilentlyContinue
    Remove-Item (Get-Agent02PidPath $RuntimeDir $Name) -Force -ErrorAction SilentlyContinue
}

function Get-Agent02ProcessRecord ([int]$Pid) {
    return Get-CimInstance Win32_Process -Filter "ProcessId = $Pid" -ErrorAction SilentlyContinue
}

function Resolve-Agent02CanonicalPath ([string]$PathValue) {
    if ([string]::IsNullOrWhiteSpace($PathValue)) {
        return ''
    }

    try {
        return [System.IO.Path]::GetFullPath($PathValue).TrimEnd('\')
    } catch {
        return [string]$PathValue
    }
}

function Test-Agent02PathEquals ([string]$LeftPath, [string]$RightPath) {
    $leftValue = Resolve-Agent02CanonicalPath $LeftPath
    $rightValue = Resolve-Agent02CanonicalPath $RightPath
    if ($leftValue -eq '' -or $rightValue -eq '') {
        return $false
    }

    return [string]::Equals($leftValue, $rightValue, [System.StringComparison]::OrdinalIgnoreCase)
}

function Test-Agent02CommandLineHasOption {
    param(
        [string[]]$CommandArgs,
        [string]$Option,
        [string]$ExpectedValue
    )

    if (-not $CommandArgs -or [string]::IsNullOrWhiteSpace($Option)) {
        return $false
    }

    $optionPrefix = "$Option="
    for ($index = 0; $index -lt $CommandArgs.Count; $index++) {
        $arg = [string]$CommandArgs[$index]
        if ([string]::Equals($arg, $Option, [System.StringComparison]::OrdinalIgnoreCase)) {
            if ($ExpectedValue -eq $null) {
                return $true
            }
            if (($index + 1) -lt $CommandArgs.Count -and [string]$CommandArgs[$index + 1] -eq $ExpectedValue) {
                return $true
            }
            continue
        }

        if ($arg.StartsWith($optionPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            if ($ExpectedValue -eq $null -or $arg.Substring($optionPrefix.Length) -eq $ExpectedValue) {
                return $true
            }
        }
    }

    return $false
}

function Get-Agent02ListeningProcessRecords ([int]$Port) {
    if (-not (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue)) {
        return @()
    }

    $connections = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Sort-Object -Property OwningProcess -Unique)
    if ($connections.Count -eq 0) {
        return @()
    }

    $records = New-Object System.Collections.Generic.List[object]
    foreach ($connection in $connections) {
        $record = Get-Agent02ProcessRecord ([int]$connection.OwningProcess)
        if ($record) {
            $records.Add($record) | Out-Null
        }
    }

    return $records.ToArray()
}

function Get-Agent02ProcessAncestry ([int]$TargetProcessId, [int]$MaxDepth = 8) {
    $records = New-Object System.Collections.Generic.List[object]
    $seen = New-Object 'System.Collections.Generic.HashSet[int]'
    $currentProcessId = $TargetProcessId

    for ($depth = 0; $depth -lt $MaxDepth -and $currentProcessId -gt 0; $depth++) {
        if (-not $seen.Add($currentProcessId)) {
            break
        }

        $record = Get-Agent02ProcessRecord $currentProcessId
        if (-not $record) {
            break
        }

        $records.Add($record) | Out-Null
        $parentProcessId = [int]$record.ParentProcessId
        if ($parentProcessId -le 0) {
            break
        }

        $currentProcessId = $parentProcessId
    }

    return $records.ToArray()
}

function Find-Agent02FallbackTracking ([string]$Name) {
    $paths = Get-Agent02Paths

    try {
        $config = Read-Agent02Config $paths.ConfigBat
    } catch {
        return $null
    }

    switch ($Name) {
        'llama-server' {
            $llamaExe = Get-Agent02ConfigValue $config 'LLAMA_SERVER_EXE'
            if ([string]::IsNullOrWhiteSpace($llamaExe)) {
                return $null
            }

            foreach ($record in @(Get-Agent02ListeningProcessRecords 8420)) {
                $commandArgs = Split-Agent02CommandLine ([string]$record.CommandLine)
                if (
                    (Test-Agent02PathEquals ([string]$record.ExecutablePath) $llamaExe) -and
                    (Test-Agent02CommandLineHasOption $commandArgs '--host' '127.0.0.1') -and
                    (Test-Agent02CommandLineHasOption $commandArgs '--port' '8420')
                ) {
                    return [pscustomobject]@{
                        pid = [int]$record.ProcessId
                        creationDate = [string]$record.CreationDate
                        stdoutLog = $null
                        stderrLog = $null
                        recovered = $true
                    }
                }
            }
        }
        'openclaw-gateway' {
            $openClawPort = Resolve-Agent02Port (Get-Agent02ConfigValue $config 'OPENCLAW_PORT') 18789
            foreach ($listenerRecord in @(Get-Agent02ListeningProcessRecords $openClawPort)) {
                foreach ($candidate in @(Get-Agent02ProcessAncestry ([int]$listenerRecord.ProcessId))) {
                    $commandLine = [string]$candidate.CommandLine
                    if ([string]::IsNullOrWhiteSpace($commandLine)) {
                        continue
                    }

                    $commandArgs = Split-Agent02CommandLine $commandLine
                    $isGatewayCommand = $commandLine.IndexOf(
                        'openclaw gateway',
                        [System.StringComparison]::OrdinalIgnoreCase
                    ) -ge 0
                    if (
                        $isGatewayCommand -and
                        (Test-Agent02CommandLineHasOption $commandArgs '--port' ([string]$openClawPort)) -and
                        (Test-Agent02CommandLineHasOption $commandArgs '--bind' 'loopback')
                    ) {
                        return [pscustomobject]@{
                            pid = [int]$candidate.ProcessId
                            creationDate = [string]$candidate.CreationDate
                            stdoutLog = $null
                            stderrLog = $null
                            recovered = $true
                        }
                    }
                }
            }
        }
    }

    return $null
}

function Get-Agent02LiveTracking ([string]$RuntimeDir, [string]$Name, [switch]$AllowRecovery) {
    $tracking = Get-Agent02Tracking $RuntimeDir $Name
    if ($tracking) {
        $record = Get-Agent02ProcessRecord ([int]$tracking.pid)
        if ($record) {
            if (-not $tracking.creationDate -or [string]$record.CreationDate -eq [string]$tracking.creationDate) {
                return [pscustomobject]@{
                    Tracking = $tracking
                    Source = 'tracked'
                }
            }
        }

        Remove-Agent02Tracking $RuntimeDir $Name
    }

    if ($AllowRecovery) {
        $recovered = Find-Agent02FallbackTracking $Name
        if ($recovered) {
            return [pscustomobject]@{
                Tracking = $recovered
                Source = 'recovered'
            }
        }
    }

    return $null
}

function Get-Agent02Tracking ([string]$RuntimeDir, [string]$Name) {
    $manifestPath = Get-Agent02ManifestPath $RuntimeDir $Name
    if (Test-Path $manifestPath) {
        try {
            return Get-Content $manifestPath -Raw | ConvertFrom-Json
        } catch {
            Remove-Agent02Tracking $RuntimeDir $Name
            return $null
        }
    }

    $pidPath = Get-Agent02PidPath $RuntimeDir $Name
    if (Test-Path $pidPath) {
        $rawPid = (Get-Content $pidPath -Raw).Trim()
        if ($rawPid -match '^\d+$') {
            return [pscustomobject]@{
                pid = [int]$rawPid
                creationDate = $null
                stdoutLog = $null
                stderrLog = $null
            }
        }
        Remove-Agent02Tracking $RuntimeDir $Name
    }

    return $null
}

function Test-Agent02TrackedProcessAlive ([string]$RuntimeDir, [string]$Name) {
    $tracking = Get-Agent02Tracking $RuntimeDir $Name
    if (-not $tracking) {
        return $false
    }

    $record = Get-Agent02ProcessRecord ([int]$tracking.pid)
    if (-not $record) {
        Remove-Agent02Tracking $RuntimeDir $Name
        return $false
    }

    if ($tracking.creationDate) {
        if ([string]$record.CreationDate -ne [string]$tracking.creationDate) {
            Remove-Agent02Tracking $RuntimeDir $Name
            return $false
        }
    }

    return $true
}

function Assert-Agent02NoTrackedProcess ([string]$RuntimeDir, [string]$Name, [string]$Label) {
    if (Test-Agent02TrackedProcessAlive $RuntimeDir $Name) {
        throw "$Label is already running. Stop it with stop-agent02.bat before launching again."
    }
}

function Save-Agent02Tracking {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RuntimeDir,

        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [System.Diagnostics.Process]$Process,

        [Parameter(Mandatory = $true)]
        [string]$Label,

        [Parameter(Mandatory = $true)]
        [string]$Command,

        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,

        [Parameter(Mandatory = $true)]
        [string]$StdOutLog,

        [Parameter(Mandatory = $true)]
        [string]$StdErrLog
    )

    Start-Sleep -Milliseconds 200
    $record = Get-Agent02ProcessRecord $Process.Id
    if (-not $record) {
        throw "$Label exited before it could be tracked."
    }

    $manifest = [ordered]@{
        label = $Label
        pid = $Process.Id
        creationDate = [string]$record.CreationDate
        executablePath = [string]$record.ExecutablePath
        commandLine = [string]$record.CommandLine
        workingDirectory = $WorkingDirectory
        command = $Command
        stdoutLog = $StdOutLog
        stderrLog = $StdErrLog
    }

    Set-Content -Path (Get-Agent02PidPath $RuntimeDir $Name) -Value $Process.Id -Encoding ASCII
    $json = $manifest | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText(
        (Get-Agent02ManifestPath $RuntimeDir $Name),
        $json,
        [System.Text.UTF8Encoding]::new($false)
    )

    return [pscustomobject]$manifest
}

function Start-Agent02Process {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RuntimeDir,

        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [string]$Label,

        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [string[]]$ArgumentList = @(),

        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,

        [Parameter(Mandatory = $true)]
        [string]$StdOutLog,

        [Parameter(Mandatory = $true)]
        [string]$StdErrLog,

        [Parameter(Mandatory = $true)]
        [string]$Command
    )

    Assert-Agent02NoTrackedProcess $RuntimeDir $Name $Label

    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput $StdOutLog `
        -RedirectStandardError $StdErrLog `
        -PassThru

    Start-Sleep -Milliseconds 300
    if ($process.HasExited) {
        throw "$Label exited immediately. See logs: $StdOutLog and $StdErrLog"
    }

    return Save-Agent02Tracking `
        -RuntimeDir $RuntimeDir `
        -Name $Name `
        -Process $process `
        -Label $Label `
        -Command $Command `
        -WorkingDirectory $WorkingDirectory `
        -StdOutLog $StdOutLog `
        -StdErrLog $StdErrLog
}

function Stop-Agent02TrackedProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RuntimeDir,

        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [string]$Label,

        [switch]$Quiet
    )

    $tracking = Get-Agent02Tracking $RuntimeDir $Name
    if (-not $tracking) {
        if (-not $Quiet) {
            Write-Agent02Info "No tracked $Label process was found."
        }
        return
    }

    if (-not (Test-Agent02TrackedProcessAlive $RuntimeDir $Name)) {
        if (-not $Quiet) {
            Write-Agent02Info "$Label is not running."
        }
        return
    }

    if (-not $Quiet) {
        Write-Agent02Info "Stopping $Label (PID $($tracking.pid)) ..."
    }

    $taskkillOutput = & taskkill /PID $tracking.pid /T /F 2>&1
    if ($LASTEXITCODE -ne 0 -and -not $Quiet) {
        Write-Agent02Warn ($taskkillOutput | Out-String).Trim()
    }

    Remove-Agent02Tracking $RuntimeDir $Name

    if (-not $Quiet) {
        Write-Agent02Ok "$Label stopped."
    }
}

function Wait-Agent02Health {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,

        [Parameter(Mandatory = $true)]
        [int]$TimeoutSeconds,

        [Parameter(Mandatory = $true)]
        [scriptblock]$AliveCheck
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (-not (& $AliveCheck)) {
            return $false
        }

        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
                return $true
            }
        } catch {
        }

        Start-Sleep -Seconds 2
    }

    return $false
}

function Wait-Agent02PortOpen {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Host,

        [Parameter(Mandatory = $true)]
        [int]$Port,

        [Parameter(Mandatory = $true)]
        [int]$TimeoutSeconds,

        [Parameter(Mandatory = $true)]
        [scriptblock]$AliveCheck
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (-not (& $AliveCheck)) {
            return $false
        }

        $client = New-Object System.Net.Sockets.TcpClient
        try {
            $async = $client.BeginConnect($Host, $Port, $null, $null)
            if ($async.AsyncWaitHandle.WaitOne(1000, $false) -and $client.Connected) {
                $client.EndConnect($async) | Out-Null
                return $true
            }
        } catch {
        } finally {
            $client.Dispose()
        }

        Start-Sleep -Seconds 2
    }

    return $false
}

function Invoke-Agent02DashboardCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$OpenClawDir,

        [Parameter(Mandatory = $true)]
        [bool]$NoOpen
    )

    $command = if ($NoOpen) {
        'pnpm openclaw dashboard --no-open'
    } else {
        'pnpm openclaw dashboard'
    }

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = 'cmd.exe'
    $startInfo.Arguments = "/d /c $command"
    $startInfo.WorkingDirectory = $OpenClawDir
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true

    $process = [System.Diagnostics.Process]::Start($startInfo)
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()

    $dashboardUrl = $null
    $combined = ($stdout + [Environment]::NewLine + $stderr)
    if ($combined -match 'Dashboard URL:\s*(\S+)') {
        $dashboardUrl = $Matches[1]
    }

    return [pscustomobject]@{
        ExitCode = $process.ExitCode
        DashboardUrl = $dashboardUrl
        StdOut = $stdout.Trim()
        StdErr = $stderr.Trim()
        Command = $command
    }
}
'@
#>
