# Create a "Claude with Kiro" shortcut on the Desktop that:
#   1. Ensures the local gateway is running
#   2. Launches Claude Desktop
#
# Usage:
#   windows\gw-make-shortcut.ps1                       # Desktop shortcut (default)
#   windows\gw-make-shortcut.ps1 -Location StartMenu   # Start Menu shortcut
#   windows\gw-make-shortcut.ps1 -Location Both        # both places
#   windows\gw-make-shortcut.ps1 -Name "Claude"        # override display name

param(
    [ValidateSet('Desktop', 'StartMenu', 'Both')]
    [string]$Location = 'Desktop',
    [string]$Name = 'Claude with Kiro'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $repo 'windows\gw-launch-claude.ps1'
if (-not (Test-Path -LiteralPath $launcher)) {
    Write-Host "Missing $launcher" -ForegroundColor Red
    exit 1
}

# Try to use Claude Desktop's real icon so the shortcut looks right.
$iconSource = $null
$claudeAppx = Get-AppxPackage -Name 'Claude' -ErrorAction SilentlyContinue
if ($claudeAppx) {
    $exe = Join-Path $claudeAppx.InstallLocation 'app\Claude.exe'
    if (Test-Path -LiteralPath $exe) { $iconSource = $exe }
}

$targets = @()
switch ($Location) {
    'Desktop'   { $targets += [Environment]::GetFolderPath('Desktop') }
    'StartMenu' { $targets += Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs' }
    'Both' {
        $targets += [Environment]::GetFolderPath('Desktop')
        $targets += Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
    }
}

$shell = New-Object -ComObject WScript.Shell
foreach ($dir in $targets) {
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    $lnk = Join-Path $dir "$Name.lnk"
    $sc = $shell.CreateShortcut($lnk)
    $sc.TargetPath = 'powershell.exe'
    $sc.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$launcher`""
    $sc.WorkingDirectory = $repo
    $sc.WindowStyle = 7  # minimized (7 = minimized, no focus); combined with -WindowStyle Hidden the console stays gone
    if ($iconSource) { $sc.IconLocation = "$iconSource,0" }
    $sc.Description = 'Start kiro-gateway (if needed) and open Claude Desktop.'
    $sc.Save()
    Write-Host "Created: $lnk" -ForegroundColor Green
}

Write-Host ""
Write-Host "Pin the shortcut to Taskbar / Start:"
Write-Host "  Right-click the shortcut  ->  Pin to taskbar (or Pin to Start)."
