# Start kiro-gateway in the background (detached), log to %TEMP%.
# Usage:
#   windows\gw-start.ps1              # start on default port
#   windows\gw-start.ps1 -Port 9000   # start on custom port
#   windows\gw-start.ps1 -Foreground  # run in current window (Ctrl+C to stop)

param(
    [int]$Port = 8787,
    [switch]$Foreground
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $env:TEMP 'kiro-gateway.pid'
$logOut  = Join-Path $env:TEMP 'kiro-gateway.log'
$logErr  = Join-Path $env:TEMP 'kiro-gateway.log.err'

# Check if already running
if (Test-Path -LiteralPath $pidFile) {
    $existingPid = (Get-Content -LiteralPath $pidFile -Raw).Trim()
    if ($existingPid -and (Get-Process -Id $existingPid -ErrorAction SilentlyContinue)) {
        $listening = Get-NetTCPConnection -OwningProcess $existingPid -State Listen -ErrorAction SilentlyContinue
        if ($listening) {
            Write-Host "Already running (PID $existingPid, port $($listening.LocalPort | Select-Object -First 1))." -ForegroundColor Yellow
            Write-Host "Use windows\gw-stop.ps1 first if you want a restart."
            exit 0
        }
    }
}

$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
$env:SERVER_PORT = $Port

if ($Foreground) {
    Write-Host "Starting kiro-gateway in foreground on 127.0.0.1:$Port (Ctrl+C to stop)..." -ForegroundColor Cyan
    Push-Location $repo
    try {
        & python main.py
    } finally {
        Pop-Location
    }
    exit
}

# Remove old logs so tail is clean
foreach ($f in @($logOut, $logErr)) { if (Test-Path -LiteralPath $f) { Remove-Item -LiteralPath $f -Force } }

$p = Start-Process -FilePath python `
                   -ArgumentList 'main.py' `
                   -WorkingDirectory $repo `
                   -RedirectStandardOutput $logOut `
                   -RedirectStandardError  $logErr `
                   -WindowStyle Hidden `
                   -PassThru
$p.Id | Out-File -LiteralPath $pidFile -Encoding ascii

Write-Host "Launched python main.py (PID $($p.Id)). Waiting for port $Port..." -ForegroundColor Cyan

$deadline = (Get-Date).AddSeconds(20)
while ((Get-Date) -lt $deadline) {
    if ($p.HasExited) {
        Write-Host "Process exited early. See:" -ForegroundColor Red
        Write-Host "  $logErr"
        Get-Content -LiteralPath $logErr -Tail 20
        exit 1
    }
    $listening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listening) {
        Write-Host "[UP] listening on 127.0.0.1:$Port (PID $($p.Id))" -ForegroundColor Green
        Write-Host "logs: $logErr"
        Write-Host "check: windows\gw-status.ps1"
        Write-Host "stop:  windows\gw-stop.ps1"
        exit 0
    }
    Start-Sleep -Milliseconds 500
}

Write-Host "Timed out waiting for port $Port. Server may still be starting." -ForegroundColor Yellow
Write-Host "See $logErr"
exit 2
