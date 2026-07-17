# Create a "Claude with Kiro" shortcut that:
#   1. Ensures the local gateway is running
#   2. Launches Claude Desktop
#
# Usage:
#   windows\gw-make-shortcut.ps1                       # Desktop shortcut (default)
#   windows\gw-make-shortcut.ps1 -Location StartMenu   # Start Menu shortcut
#   windows\gw-make-shortcut.ps1 -Location Both        # both places
#   windows\gw-make-shortcut.ps1 -Name "Claude"        # override display name
#
# Icon strategy:
#   Claude Desktop is a Microsoft Store (Appx) app whose install path is
#   version-scoped (e.g. Claude_1.22209.0.0_x64__pzs8sxrjxfjjc). If we bake
#   that versioned path into the shortcut, the icon breaks on every Claude
#   update. So we extract Claude.exe's icon once into a stable local .ico
#   under the repo and point the shortcut at that. As a fallback we still
#   reference the live Appx path (works today, breaks on update). Re-run this
#   script after a Claude major update to refresh the .ico if you want.

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

# Resolve Claude Desktop install path via Appx (version-independent) so a
# Claude update doesn't leave the shortcut with a dead icon reference.
function Get-ClaudeExePath {
    $pkg = Get-AppxPackage -Name 'Claude' -ErrorAction SilentlyContinue |
        Sort-Object -Property Version -Descending |
        Select-Object -First 1
    if (-not $pkg) { return $null }
    $exe = Join-Path $pkg.InstallLocation 'app\Claude.exe'
    if (Test-Path -LiteralPath $exe) { return $exe }
    return $null
}

# Extract Claude.exe's first icon to a stable path in the repo, so the
# shortcut survives Claude version bumps.
function Export-ClaudeIcon {
    param([string]$SourceExe, [string]$DestIco)
    try {
        Add-Type -AssemblyName System.Drawing
        $icon = [System.Drawing.Icon]::ExtractAssociatedIcon($SourceExe)
        if (-not $icon) { return $false }
        $fs = [System.IO.File]::Open($DestIco, 'Create')
        try { $icon.Save($fs) } finally { $fs.Dispose(); $icon.Dispose() }
        return (Test-Path -LiteralPath $DestIco)
    } catch {
        Write-Host "  (icon extract failed: $($_.Exception.Message))" -ForegroundColor DarkYellow
        return $false
    }
}

$iconLocation = $null
$claudeExe = Get-ClaudeExePath
if ($claudeExe) {
    $icoDir = Join-Path $repo 'windows'
    $icoPath = Join-Path $icoDir 'claude.ico'
    if (Export-ClaudeIcon -SourceExe $claudeExe -DestIco $icoPath) {
        $iconLocation = "$icoPath,0"
        Write-Host "Extracted icon: $icoPath" -ForegroundColor DarkGray
    } else {
        # Fallback: point at the live Appx exe. Works until Claude updates.
        $iconLocation = "$claudeExe,0"
    }
} else {
    Write-Host "Claude Desktop not found via Appx - shortcut will use default PowerShell icon." -ForegroundColor Yellow
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
    # Delete stale shortcut first - avoids Explorer caching the old (dead) icon path.
    if (Test-Path -LiteralPath $lnk) { Remove-Item -LiteralPath $lnk -Force }

    $sc = $shell.CreateShortcut($lnk)
    $sc.TargetPath = 'powershell.exe'
    $sc.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$launcher`""
    $sc.WorkingDirectory = $repo
    $sc.WindowStyle = 7  # minimized (7 = minimized, no focus); combined with -WindowStyle Hidden the console stays gone
    if ($iconLocation) { $sc.IconLocation = $iconLocation }
    $sc.Description = 'Start kiro-gateway (if needed) and open Claude Desktop.'
    $sc.Save()
    Write-Host "Created: $lnk" -ForegroundColor Green
}

# Nudge Explorer to refresh icon cache for the new shortcuts.
try {
    $sig = @'
[System.Runtime.InteropServices.DllImport("shell32.dll")]
public static extern void SHChangeNotify(int wEventId, int uFlags, System.IntPtr dwItem1, System.IntPtr dwItem2);
'@
    $shell32 = Add-Type -MemberDefinition $sig -Name Shell32Notify -Namespace Win32Utils -PassThru -ErrorAction SilentlyContinue
    if ($shell32) {
        # SHCNE_ASSOCCHANGED = 0x08000000, SHCNF_IDLIST = 0x0000
        $shell32::SHChangeNotify(0x08000000, 0, [System.IntPtr]::Zero, [System.IntPtr]::Zero)
    }
} catch { }

Write-Host ""
Write-Host "Pin the shortcut to Taskbar / Start:"
Write-Host "  Right-click the shortcut  ->  Pin to taskbar (or Pin to Start)."
