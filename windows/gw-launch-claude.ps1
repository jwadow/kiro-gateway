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
    [string]$ClaudeAppId = 'Claude_pzs8sxrjxfjjc!Claude'
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

# 2) Launch Claude Desktop via its AppUserModelID (works for Store/Appx installs).
try {
    # Use the shell activate-application helper. Reliable for packaged apps.
    Start-Process -FilePath ("shell:AppsFolder\$ClaudeAppId")
} catch {
    Write-Host "[claude] failed to launch via AppsFolder: $($_.Exception.Message)" -ForegroundColor Red
    # Last-resort fallback: try explorer.exe with the same URI.
    Start-Process -FilePath 'explorer.exe' -ArgumentList "shell:AppsFolder\$ClaudeAppId"
}