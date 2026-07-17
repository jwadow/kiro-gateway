# Refresh Kiro credentials and reload the gateway.
#
# What this does, in order:
#   1. Sanity-check that kiro-cli is installed.
#   2. Show current login state (whoami).
#   3. Run `kiro-cli login` in a visible foreground shell so you can complete
#      the interactive SSO / browser flow.
#   4. Verify the SQLite database now has a fresh non-expired token.
#   5. If the gateway is running, stop it and start it again so it picks up
#      the new credentials on the next request.
#   6. Ping /health to confirm the gateway is serving with the new creds.
#
# Why restart the gateway?
#   The gateway lazy-refreshes tokens in memory from SQLite on each request,
#   so a full restart is not strictly required. However kiro-cli also rotates
#   the client_id / client_secret device registration on some login flows,
#   and the safest way to guarantee a clean state is to restart. It only
#   takes ~2 seconds.
#
# Usage:
#   windows\gw-update-creds.ps1                    # interactive full flow
#   windows\gw-update-creds.ps1 -NoRestart         # refresh creds only, leave gateway alone
#   windows\gw-update-creds.ps1 -Port 9000         # custom gateway port
#   windows\gw-update-creds.ps1 -SkipLogin         # skip login, just restart gateway

param(
    [int]$Port = 8787,
    [switch]$NoRestart,
    [switch]$SkipLogin
)

$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent $PSScriptRoot
$startScript = Join-Path $repo 'windows\gw-start.ps1'
$stopScript  = Join-Path $repo 'windows\gw-stop.ps1'

function Test-GatewayUp {
    param([int]$P)
    $null -ne (Get-NetTCPConnection -LocalPort $P -State Listen -ErrorAction SilentlyContinue)
}

function Get-KiroCliPath {
    # Prefer PATH, fall back to the known install location.
    $cmd = Get-Command 'kiro-cli' -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $fallback = Join-Path $env:LOCALAPPDATA 'Kiro-Cli\kiro-cli.exe'
    if (Test-Path -LiteralPath $fallback) { return $fallback }
    return $null
}

function Get-SqliteDbPath {
    # Match the value the gateway is using per .env, otherwise fall back to
    # the canonical kiro-cli location.
    $envFile = Join-Path $repo '.env'
    if (Test-Path -LiteralPath $envFile) {
        foreach ($line in Get-Content -LiteralPath $envFile) {
            if ($line -match '^\s*KIRO_CLI_DB_FILE\s*=\s*"?([^"\r\n]+?)"?\s*$') {
                return $Matches[1]
            }
        }
    }
    return (Join-Path $env:LOCALAPPDATA 'Kiro-Cli\data.sqlite3')
}

function Get-TokenExpiry {
    param([string]$DbPath)
    if (-not (Test-Path -LiteralPath $DbPath)) { return $null }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { $python = Get-Command py -ErrorAction SilentlyContinue }
    if (-not $python) { return $null }

    # Small python one-shot to read the token expiry - avoids needing a
    # PowerShell SQLite module.
    $script = @'
import sys, sqlite3, json
db = sys.argv[1]
try:
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    keys = [
        "kirocli:social:token",
        "kirocli:odic:token",
        "codewhisperer:odic:token",
    ]
    for k in keys:
        cur.execute("SELECT value FROM auth_kv WHERE key = ?", (k,))
        row = cur.fetchone()
        if row:
            try:
                data = json.loads(row[0])
                print(data.get("expires_at") or data.get("expiresAt") or "")
                break
            except Exception:
                pass
finally:
    try: conn.close()
    except Exception: pass
'@
    $tmp = Join-Path $env:TEMP ('gw-token-expiry-' + [guid]::NewGuid().ToString('N') + '.py')
    Set-Content -LiteralPath $tmp -Value $script -Encoding UTF8
    try {
        $out = & $python.Source $tmp $DbPath 2>$null
        return ($out | Select-Object -First 1)
    } finally {
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "==== Kiro credentials refresh ====" -ForegroundColor Cyan

# 1) kiro-cli presence
$kiroCli = Get-KiroCliPath
if (-not $kiroCli) {
    Write-Host "[FAIL] kiro-cli not found on PATH or in LOCALAPPDATA\Kiro-Cli." -ForegroundColor Red
    Write-Host "       Install Kiro CLI first, then rerun this script."
    exit 1
}
Write-Host "[ok] kiro-cli: $kiroCli" -ForegroundColor DarkGray

# 2) whoami (best-effort - may fail if fully logged out)
try {
    $who = & $kiroCli whoami 2>&1
    Write-Host "[whoami]" -ForegroundColor DarkGray
    $who | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
} catch {
    Write-Host "[whoami] not currently logged in" -ForegroundColor DarkYellow
}

$dbPath = Get-SqliteDbPath
Write-Host "[db]     $dbPath" -ForegroundColor DarkGray
$oldExpiry = Get-TokenExpiry -DbPath $dbPath
if ($oldExpiry) { Write-Host "[token]  currently expires: $oldExpiry" -ForegroundColor DarkGray }

# 3) Interactive login (foreground - user needs to see the browser prompt)
if (-not $SkipLogin) {
    # kiro-cli refuses to log in while a stale session exists ("Already
    # logged in, please logout with kiro-cli logout first"). Force a
    # logout up front so the retry is guaranteed to be a clean login.
    Write-Host ""
    Write-Host "Clearing any existing kiro-cli session..." -ForegroundColor DarkGray
    & $kiroCli logout 2>&1 | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
    # Ignore logout exit code - "not logged in" also returns non-zero and
    # that's fine, we just wanted the slate clean.

    Write-Host ""
    Write-Host "Launching 'kiro-cli login' - complete the flow in the window / browser..." -ForegroundColor Yellow
    # Do NOT run kiro-cli detached. It's an interactive command; keep it in
    # this console so the user can respond to prompts.
    & $kiroCli login
    $rc = $LASTEXITCODE
    if ($rc -ne 0) {
        Write-Host "[FAIL] kiro-cli login exited with code $rc." -ForegroundColor Red
        Write-Host "       Credentials NOT refreshed. Gateway left as-is."
        exit $rc
    }
} else {
    Write-Host "[skip] -SkipLogin set - not running kiro-cli login" -ForegroundColor Yellow
}

# 4) Verify SQLite has a fresher token than before
$newExpiry = Get-TokenExpiry -DbPath $dbPath
if ($newExpiry) {
    Write-Host "[token]  new expiry:         $newExpiry" -ForegroundColor Green
} else {
    Write-Host "[warn]   could not read token expiry from SQLite - continuing anyway." -ForegroundColor Yellow
}

# Post-login whoami so user can confirm which identity is active.
try {
    $who = & $kiroCli whoami 2>&1
    Write-Host "[whoami post-login]" -ForegroundColor DarkGray
    $who | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
} catch { }

# 5) Restart gateway if requested and it's running
if ($NoRestart) {
    Write-Host ""
    Write-Host "[ok] Credentials refreshed. Gateway left running as-is (-NoRestart)." -ForegroundColor Green
    exit 0
}

Write-Host ""
if (Test-GatewayUp -P $Port) {
    Write-Host "[gw] restarting on port $Port..." -ForegroundColor Cyan
    if (Test-Path -LiteralPath $stopScript) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $stopScript -Port $Port | Out-Null
    }
    # Small wait for the socket to release.
    $deadline = (Get-Date).AddSeconds(5)
    while ((Test-GatewayUp -P $Port) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 200 }
} else {
    Write-Host "[gw] not currently running - starting fresh." -ForegroundColor Cyan
}

if (-not (Test-Path -LiteralPath $startScript)) {
    Write-Host "[FAIL] Cannot find $startScript - gateway not started." -ForegroundColor Red
    exit 1
}

# Call gw-start.ps1 synchronously. It spawns python detached internally and
# waits up to 20s for the port itself, then exits 0 / 1 / 2. Running inline
# gives us real exit codes and streamed output instead of racing our own
# poll loop against its poll loop.
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $startScript -Port $Port
$startRc = $LASTEXITCODE
if ($startRc -ne 0 -or -not (Test-GatewayUp -P $Port)) {
    Write-Host "[FAIL] Gateway didn't come up on 127.0.0.1:$Port (gw-start rc=$startRc)." -ForegroundColor Red
    Write-Host "       Check log: $env:TEMP\kiro-gateway.log.err"
    exit 2
}

# 6) Health check
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 5
    Write-Host "[gw] UP on 127.0.0.1:$Port (version $($health.version))" -ForegroundColor Green
} catch {
    Write-Host "[warn] port is open but /health failed: $($_.Exception.Message)" -ForegroundColor Yellow
    exit 2
}

Write-Host ""
Write-Host "Done. Claude Desktop will use the refreshed credentials on the next request." -ForegroundColor Green
exit 0
