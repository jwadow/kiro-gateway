# Simple status check for kiro-gateway.
# Usage:
#   windows\gw-status.ps1              # default port 8000
#   windows\gw-status.ps1 -Port 9000

param(
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'

function Get-ApiKeyFromEnv {
    $envPath = Join-Path (Split-Path -Parent $PSScriptRoot) ".env"
    if (-not (Test-Path -LiteralPath $envPath)) { return $null }
    foreach ($line in Get-Content -LiteralPath $envPath) {
        if ($line -match '^\s*PROXY_API_KEY\s*=\s*"?([^"\r\n]+?)"?\s*$') {
            return $Matches[1]
        }
    }
    return $null
}

$listening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $listening) {
    Write-Host "[DOWN] Nothing is listening on 127.0.0.1:$Port" -ForegroundColor Red
    exit 1
}

$pidValue = $listening.OwningProcess | Select-Object -First 1
$proc = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
Write-Host "[LISTENING] 127.0.0.1:$Port (PID $pidValue $($proc.ProcessName))" -ForegroundColor Green

Write-Host "`n== GET /health ==" -ForegroundColor Cyan
try {
    (Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 5) | ConvertTo-Json -Compress | Write-Output
} catch {
    Write-Host "  ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 2
}

$apiKey = Get-ApiKeyFromEnv
if (-not $apiKey) {
    Write-Host "`n(no PROXY_API_KEY in .env, skipping authenticated endpoints)" -ForegroundColor Yellow
    exit 0
}

Write-Host "`n== GET /v1/models (x-api-key) ==" -ForegroundColor Cyan
try {
    $models = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/v1/models" -Headers @{ 'x-api-key' = $apiKey } -TimeoutSec 5
    Write-Host ("  {0} models" -f $models.data.Count)
    $models.data | Select-Object -First 6 id, display_name | Format-Table -AutoSize
} catch {
    Write-Host "  ERROR: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "== POST /v1/messages (ping-sized round trip) ==" -ForegroundColor Cyan
$body = @{
    model      = 'claude-haiku-4.5'
    max_tokens = 32
    messages   = @(@{ role = 'user'; content = 'ping' })
} | ConvertTo-Json -Depth 5
try {
    $resp = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/v1/messages" -Method POST -Headers @{
        'x-api-key'         = $apiKey
        'anthropic-version' = '2023-06-01'
        'Content-Type'      = 'application/json'
    } -Body $body -TimeoutSec 60
    $text = ($resp.content | Where-Object { $_.type -eq 'text' } | Select-Object -First 1).text
    Write-Host ("  stop_reason={0}  input={1}  output={2}" -f $resp.stop_reason, $resp.usage.input_tokens, $resp.usage.output_tokens)
    if ($text) { Write-Host "  reply: $($text.Substring(0, [Math]::Min(200, $text.Length)))" }
} catch {
    Write-Host "  ERROR: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.ErrorDetails) { Write-Host "  body: $($_.ErrorDetails.Message)" -ForegroundColor DarkYellow }
}
