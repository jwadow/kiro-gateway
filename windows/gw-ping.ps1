# Instant liveness check for kiro-gateway. Returns in under a second.
# Does NOT hit Kiro's servers - only checks the local port + /health.
#
# Usage:
#   windows\gw-ping.ps1              # default port 8000
#   windows\gw-ping.ps1 -Port 9000

param(
    [int]$Port = 8000
)

$ErrorActionPreference = 'SilentlyContinue'

$listening = Get-NetTCPConnection -LocalPort $Port -State Listen
if (-not $listening) {
    Write-Host "DOWN" -ForegroundColor Red
    exit 1
}

$pidValue = $listening.OwningProcess | Select-Object -First 1
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2
    Write-Host "UP (PID $pidValue, version $($health.version))" -ForegroundColor Green
    exit 0
} catch {
    Write-Host "PORT-BUSY-BUT-NOT-HEALTHY (PID $pidValue)" -ForegroundColor Yellow
    exit 2
}
