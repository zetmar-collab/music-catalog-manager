param([switch]$ResumeExisting, [string]$InnoCompiler = '')
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$InstallTarget = Join-Path $ProjectRoot 'build\installation-acceptance-0.4.0'
$TestProfile = Join-Path $ProjectRoot 'build\installer-test-profile-0.4.0'
$ReportPath = Join-Path $ProjectRoot 'reports\installer-result.json'
if ((Test-Path -LiteralPath $InstallTarget) -and -not $ResumeExisting) { throw 'Test installation destination already exists; choose a fresh test directory' }
$SetupExe = Join-Path $ProjectRoot 'build\MusicCatalogManager-Acceptance-Setup.exe'
if (-not $ResumeExisting) {
    if (-not $InnoCompiler) { $InnoCompiler = Join-Path $ProjectRoot 'tools\InnoSetup\ISCC.exe' }
    & $InnoCompiler /DAcceptanceTest (Join-Path $PSScriptRoot 'installer.iss')
    if ($LASTEXITCODE -ne 0) { throw 'Acceptance installer compilation failed' }
    $SetupProcess = Start-Process -FilePath $SetupExe -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CURRENTUSER', ('/DIR="' + $InstallTarget + '"')) -WindowStyle Hidden -PassThru -Wait
    $SetupProcess.Refresh()
    if ($SetupProcess.ExitCode -ne 0) { throw 'Installer failed' }
}
$ShortcutPath = Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs\Music Catalog Manager Acceptance Test 0.4.0\Music Catalog Manager.lnk'
if (-not (Test-Path -LiteralPath $ShortcutPath)) { throw 'Start Menu shortcut missing' }
$Shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($ShortcutPath)
if ($Shortcut.TargetPath -ne (Join-Path $InstallTarget 'MusicCatalogManager.exe')) { throw 'Wrong shortcut target' }
$OriginalPath = $env:PATH
try {
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    $AppProcess = Start-Process -FilePath (Join-Path $InstallTarget 'MusicCatalogManager.exe') -ArgumentList @('--smoke-test', '--profile', ('"' + $TestProfile + '"')) -WindowStyle Hidden -PassThru
    if (-not $AppProcess.WaitForExit(30000)) { Stop-Process -Id $AppProcess.Id; throw 'Installed application timeout' }
    $AppProcess.Refresh()
    if ($AppProcess.ExitCode -ne 0) { throw 'Installed application failed' }
} finally { $env:PATH = $OriginalPath }
$SmokeResult = Get-Content -LiteralPath (Join-Path $TestProfile 'smoke-result.json') -Raw | ConvertFrom-Json
if (-not $SmokeResult.window_visible -or -not $SmokeResult.icon_loaded) { throw 'Installed application verification failed' }
$UninstallProcess = Start-Process -FilePath (Join-Path $InstallTarget 'unins000.exe') -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') -WindowStyle Hidden -PassThru -Wait
$UninstallProcess.Refresh()
if ($UninstallProcess.ExitCode -ne 0) { throw 'Uninstaller failed' }
if (Test-Path -LiteralPath (Join-Path $InstallTarget 'MusicCatalogManager.exe')) { throw 'Uninstall did not remove the application' }
if (Test-Path -LiteralPath $ShortcutPath) { throw 'Shortcut remains after uninstall' }
if (-not (Test-Path -LiteralPath (Join-Path $TestProfile 'library.sqlite'))) { throw 'Test catalog was removed by uninstall' }
@{ installed = $true; shortcut = $true; launched = $true; icon = $true; uninstalled = $true; catalog_preserved = $true; isolated_clean_windows = $false; separate_acceptance_app_id = $true } | ConvertTo-Json | Set-Content -LiteralPath $ReportPath -Encoding UTF8
Get-Content -LiteralPath $ReportPath
