$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
$OriginalPath = $env:PATH
try {
    & .\.venv\Scripts\python.exe scripts\release.py --check --stamp
    if ($LASTEXITCODE -ne 0) { throw 'Release metadata validation failed' }
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$ProjectRoot\.venv\Scripts"
    & .\.venv\Scripts\python.exe -m PyInstaller --noconfirm MusicCatalogManager.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
} finally {
    $env:PATH = $OriginalPath
    Pop-Location
}
