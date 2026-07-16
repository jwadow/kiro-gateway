# Stop the background kiro-gateway process launched by gw-start.ps1.
# Usage: windows\gw-stop.ps1

param(
    [int]$Port = 8000
)

$ErrorActionPreference = 'SilentlyContinue'
$pidFile = Join-Path $env:TEMP 'kiro-gateway.pid'
$stopped = @()

# 1) Kill by pid file (preferred)
if (Test-Path -LiteralPath $pidFile) {
    $pidValue = (Get-Content -LiteralPath $pidFile -Raw).Trim()
    if ($pidValue -and (Get-Process -Id $pidValue -ErrorAction SilentlyContinue)) {
        Stop-Process -Id $pidValue -Force
        $stopped += $pidValue
    }
    Remove-Item -LiteralPath $pidFile -Force
}

# 2) Fallback: kill whatever holds the port
$listening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
foreach ($conn in $listening) {
    $ownerPid = $conn.OwningProcess
    if ($ownerPid -and (Get-Process -Id $ownerPid -ErrorAction SilentlyContinue)) {
        Stop-Process -Id $ownerPid -Force
        if ($stopped -notcontains $ownerPid) { $stopped += $ownerPid }
    }
}

if ($stopped.Count -gt 0) {
    Write-Host "Stopped PID(s): $($stopped -join ', ')" -ForegroundColor Green
} else {
    Write-Host "Nothing to stop (no running gateway found)." -ForegroundColor Yellow
}
