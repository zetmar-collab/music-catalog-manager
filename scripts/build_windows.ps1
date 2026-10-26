param([string]$InnoCompiler = '', [switch]$SkipInstaller)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
    if (-not (Test-Path '.venv\Scripts\python.exe')) { py -3.12 -m venv .venv }
    $PythonExe = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        uv pip install --python $PythonExe -r requirements-lock.txt
        if ($LASTEXITCODE -ne 0) { throw 'Locked dependency installation failed' }
        uv pip install --python $PythonExe --no-deps -e .
    } else {
        & $PythonExe -m pip install -r requirements-lock.txt
        if ($LASTEXITCODE -ne 0) { throw 'Locked dependency installation failed' }
        & $PythonExe -m pip install --no-deps -e .
    }
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    & $PythonExe scripts\make_icon.py
    if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed' }
    & $PythonExe scripts\collect_licenses.py
    if ($LASTEXITCODE -ne 0) { throw 'License collection failed' }
    New-Item -ItemType Directory -Path reports -Force | Out-Null
    & $PythonExe -m pytest -q --junitxml=reports\pytest.xml
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
    $BuildPathOriginal = $env:PATH
    try {
        $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$ProjectRoot\.venv\Scripts"
        & $PythonExe -m PyInstaller --clean --noconfirm MusicCatalogManager.spec
    } finally { $env:PATH = $BuildPathOriginal }
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
    $SmokeProfile = Join-Path $ProjectRoot 'build\smoke-profile'
    $SmokeProcess = Start-Process -FilePath 'dist\MusicCatalogManager\MusicCatalogManager.exe' -ArgumentList @('--smoke-test', '--profile', ('"' + $SmokeProfile + '"')) -WindowStyle Hidden -PassThru
    if (-not $SmokeProcess.WaitForExit(30000)) { Stop-Process -Id $SmokeProcess.Id; throw 'EXE startup did not finish within 30 seconds' }
    $SmokeProcess.Refresh()
    if ($SmokeProcess.ExitCode -ne 0) { throw 'EXE smoke test failed' }
    & $PythonExe scripts\make_playback_fixture.py
    if ($LASTEXITCODE -ne 0) { throw 'Playback fixture generation failed' }
    $PlaybackProcess = Start-Process -FilePath 'dist\MusicCatalogManager\MusicCatalogManager.exe' -ArgumentList @('--verify-playback', 'build\playback-smoke-audio', '--profile', ('"' + $SmokeProfile + '"')) -WindowStyle Hidden -PassThru
    if (-not $PlaybackProcess.WaitForExit(30000)) { Stop-Process -Id $PlaybackProcess.Id; throw 'Packaged playback timeout' }
    $PlaybackProcess.Refresh()
    if ($PlaybackProcess.ExitCode -ne 0) { throw 'Packaged playback failed' }
    $PlaybackReport = Get-Content -LiteralPath (Join-Path $SmokeProfile 'playback-result.json') -Raw | ConvertFrom-Json
    if (-not $PlaybackReport.passed) { throw 'Packaged playback verification failed' }
    if (-not $SkipInstaller) {
        if (-not $InnoCompiler) {
            $Candidates = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", (Join-Path $ProjectRoot 'tools\InnoSetup\ISCC.exe'))
            $InnoCompiler = $Candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
        }
        if (-not $InnoCompiler) { throw 'Install Inno Setup or pass -InnoCompiler with the path to ISCC.exe' }
        & $InnoCompiler scripts\installer.iss
        if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
    }
} finally { Pop-Location }
