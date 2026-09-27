# ==============================================================================
# Tally Server Pro - Isolated Build Script
# ==============================================================================
# Builds the standalone Windows Executable using an external temp directory
# to prevent Dropbox synchronization file locks.
# ==============================================================================

$ErrorActionPreference = "Stop"

$ProjectDir = $PSScriptRoot
$ExternalTempDir = Join-Path $env:TEMP "ATEMTallyServer_Build"
$DistDir = Join-Path $ProjectDir "dist"

Write-Host ">>> Preparing isolated build directory: $ExternalTempDir"
if (Test-Path $ExternalTempDir) {
    Remove-Item -Recurse -Force $ExternalTempDir -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Path $ExternalTempDir -Force | Out-Null

# Copy source and asset files to external temp directory
Copy-Item -Path (Join-Path $ProjectDir "*.py") -Destination $ExternalTempDir
Copy-Item -Path (Join-Path $ProjectDir "*.ico") -Destination $ExternalTempDir
Copy-Item -Path (Join-Path $ProjectDir "*.png") -Destination $ExternalTempDir
Copy-Item -Path (Join-Path $ProjectDir "static") -Destination $ExternalTempDir -Recurse

# Execute PyInstaller in external temp folder
$prevPwd = Get-Location
try {
    Set-Location $ExternalTempDir

    Write-Host ">>> Running PyInstaller build..."
    python -m PyInstaller --noconfirm --clean --onefile --windowed `
        --icon "Tally.ico" `
        --add-data "static;static" `
        --add-data "Tally.ico;." `
        --add-data "Tally.png;." `
        --add-data "Config.ico;." `
        --add-data "Config.png;." `
        --add-data "Help.ico;." `
        --add-data "Help.png;." `
        --hidden-import "qrcode" `
        --hidden-import "qrcode.image.pil" `
        --hidden-import "PIL._tkinter_finder" `
        --name "TallyServerPro" `
        "app.py"

    # Copy output executable back to project dist folder
    if (!(Test-Path $DistDir)) {
        New-Item -ItemType Directory -Path $DistDir -Force | Out-Null
    }

    $BuiltExe = Join-Path $ExternalTempDir "dist\TallyServerPro.exe"
    if (Test-Path $BuiltExe) {
        Copy-Item -Path $BuiltExe -Destination (Join-Path $DistDir "TallyServerPro.exe") -Force
        Write-Host ">>> SUCCESS: Executable generated at: $DistDir\TallyServerPro.exe" -ForegroundColor Green
    } else {
        throw "Executable was not generated at $BuiltExe"
    }
}
finally {
    Set-Location $prevPwd
    if (Test-Path $ExternalTempDir) {
        Remove-Item -Recurse -Force $ExternalTempDir -ErrorAction SilentlyContinue
    }
}
