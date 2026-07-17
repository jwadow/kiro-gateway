# Launcher: start kiro-gateway (if not already running), then open Claude Desktop.
#
# Use this as your "Claude" shortcut. It replaces the normal app launch:
# it guarantees the local gateway is up before Claude Desktop starts its
# third-party inference calls.
#
# Usage:
#   windows\gw-launch-claude.ps1                # normal launch
#   windows\gw-launch-claude.ps1 -Port 8787     # override gateway port
#   windows\gw-launch-claude.ps1 -NoWait        # don't block waiting for port
#
# Exit code 0 on success. Never blocks Claude from launching even if the
# gateway fails - Claude Desktop will just report "Gateway unreachable" and
# you can inspect logs at $env:TEMP\kiro-gateway.log.err.

param(
    [int]$Port = 8787,
    [switch]$NoWait,
    # Override the AppUserModelID if Claude Desktop ever changes it.
    # Default is discovered dynamically from Get-StartApps below - this
    # parameter is only useful as an emergency escape hatch.
    [string]$ClaudeAppId = $null
)

$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent $PSScriptRoot
$startScript = Join-Path $repo 'windows\gw-start.ps1'

function Test-GatewayUp {
    param([int]$P)
    $null -ne (Get-NetTCPConnection -LocalPort $P -State Listen -ErrorAction SilentlyContinue)
}

# 1) Ensure gateway is running
if (Test-GatewayUp -P $Port) {
    Write-Host "[gw] already up on 127.0.0.1:$Port" -ForegroundColor DarkGray
} else {
    if (Test-Path -LiteralPath $startScript) {
        Write-Host "[gw] starting..." -ForegroundColor Cyan
        # Fire-and-forget; gw-start.ps1 handles its own logs / pidfile.
        Start-Process -FilePath 'powershell.exe' `
            -ArgumentList @(
                '-NoProfile',
                '-WindowStyle', 'Hidden',
                '-ExecutionPolicy', 'Bypass',
                '-File', $startScript,
                '-Port', $Port
            ) `
            -WindowStyle Hidden | Out-Null

        if (-not $NoWait) {
            # Wait up to ~8 seconds for the port to come up. Claude Desktop's
            # first inference call is what actually matters, and it takes a
            # moment after the window appears, so a short wait here is enough.
            $deadline = (Get-Date).AddSeconds(8)
            while (-not (Test-GatewayUp -P $Port) -and (Get-Date) -lt $deadline) {
                Start-Sleep -Milliseconds 250
            }
            if (Test-GatewayUp -P $Port) {
                Write-Host "[gw] ready on 127.0.0.1:$Port" -ForegroundColor Green
            } else {
                Write-Host "[gw] not up after 8s (Claude will retry). Log: $env:TEMP\kiro-gateway.log.err" -ForegroundColor Yellow
            }
        }
    } else {
        Write-Host "[gw] cannot find $startScript - launching Claude anyway" -ForegroundColor Yellow
    }
}

# 2) Launch Claude Desktop.
# Prefer the real Appx AppUserModelID (works reliably for Store apps). Fall
# back to explorer.exe with the shell:AppsFolder URI if Start-Process refuses,
# and finally to the direct Claude.exe path as a last resort.
if (-not $ClaudeAppId) {
    try {
        $appEntry = Get-StartApps | Where-Object { $_.Name -eq 'Claude' -and $_.AppID -like 'Claude_*!Claude' } | Select-Object -First 1
        if ($appEntry) { $ClaudeAppId = $appEntry.AppID }
    } catch { }
    if (-not $ClaudeAppId) { $ClaudeAppId = 'Claude_pzs8sxrjxfjjc!Claude' }
}

$launched = $false
try {
    Start-Process -FilePath ("shell:AppsFolder\$ClaudeAppId")
    $launched = $true
} catch {
    Write-Host "[claude] Start-Process AppsFolder failed: $($_.Exception.Message)" -ForegroundColor Yellow
}

if (-not $launched) {
    try {
        Start-Process -FilePath 'explorer.exe' -ArgumentList "shell:AppsFolder\$ClaudeAppId"
        $launched = $true
    } catch {
        Write-Host "[claude] explorer AppsFolder fallback failed: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

if (-not $launched) {
    try {
        $pkg = Get-AppxPackage -Name 'Claude' -ErrorAction SilentlyContinue |
            Sort-Object -Property Version -Descending |
            Select-Object -First 1
        if ($pkg) {
            $exe = Join-Path $pkg.InstallLocation 'app\Claude.exe'
            if (Test-Path -LiteralPath $exe) {
                Start-Process -FilePath $exe
                $launched = $true
            }
        }
    } catch {
        Write-Host "[claude] direct Claude.exe fallback failed: $($_.Exception.Message)" -ForegroundColor Red
    }
}

if (-not $launched) {
    Write-Host "[claude] could not launch Claude Desktop. Is it installed?" -ForegroundColor Red
    exit 1
}