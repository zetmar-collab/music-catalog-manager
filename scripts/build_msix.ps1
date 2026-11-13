param(
    [string]$CertificateThumbprint = '',
    [string]$SdkVersion = '10.0.26100.0',
    [string]$SdkBin = ''
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $SdkBin) { $SdkBin = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin\$SdkVersion\x64" }
$MakeAppx = Join-Path $SdkBin 'makeappx.exe'
$SignTool = Join-Path $SdkBin 'signtool.exe'
foreach ($Tool in @($MakeAppx, $SignTool)) {
    if (-not (Test-Path -LiteralPath $Tool)) { throw "Windows SDK tool missing: $Tool" }
}
$ManifestPath = Join-Path $ProjectRoot 'packaging\msix\AppxManifest.xml'
[xml]$Manifest = Get-Content -LiteralPath $ManifestPath -Raw
$Identity = $Manifest.Package.Identity
$Publisher = $Identity.Publisher
$Version = $Identity.Version
$Release = Get-Content -LiteralPath (Join-Path $ProjectRoot 'src\music_catalog_manager\resources\release.json') -Raw | ConvertFrom-Json
if ($Version -ne $Release.msix_version) { throw 'Manifest version differs from release.json' }
$Bundle = Join-Path $ProjectRoot 'dist\MusicCatalogManager'
$Executable = Join-Path $Bundle 'MusicCatalogManager.exe'
if (-not (Test-Path -LiteralPath $Executable)) { throw 'Build the PyInstaller bundle first' }
$SmokeProfile = Join-Path $ProjectRoot ('build\msix-source-check-' + [guid]::NewGuid().ToString('N'))
$App = Start-Process -FilePath $Executable -ArgumentList @('--smoke-test', '--profile', ('"' + $SmokeProfile + '"')) -WindowStyle Hidden -PassThru
if (-not $App.WaitForExit(30000)) { Stop-Process -Id $App.Id; throw 'Bundle smoke check timeout' }
$App.Refresh()
if ($App.ExitCode -ne 0) { throw 'Bundle smoke check failed' }
$Smoke = Get-Content -LiteralPath (Join-Path $SmokeProfile 'smoke-result.json') -Raw | ConvertFrom-Json
$Fingerprint = & (Join-Path $ProjectRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'release.py') --fingerprint
if ($LASTEXITCODE -ne 0 -or $Smoke.version -ne $Release.version -or $Smoke.build.source_sha256 -ne $Fingerprint -or -not $Smoke.window_visible) { throw 'Stale or invalid application bundle. Run scripts/build_release.ps1 first.' }
$AvailableCertificates = @(Get-ChildItem Cert:\CurrentUser\My | Where-Object {
    $_.Subject -ceq $Publisher -and $_.HasPrivateKey -and $_.NotBefore -le (Get-Date) -and $_.NotAfter -gt (Get-Date) -and
    @($_.EnhancedKeyUsageList | Where-Object ObjectId -eq '1.3.6.1.5.5.7.3.3').Count -gt 0
})
if ($CertificateThumbprint) {
    $Certificate = $AvailableCertificates | Where-Object Thumbprint -eq $CertificateThumbprint | Select-Object -First 1
} else {
    $Certificate = $AvailableCertificates | Sort-Object NotAfter -Descending | Select-Object -First 1
}
if (-not $Certificate) { throw "No valid code-signing certificate with private key for $Publisher in CurrentUser\My" }
$Bundle = Join-Path $ProjectRoot 'dist\MusicCatalogManager'
if (-not (Test-Path -LiteralPath (Join-Path $Bundle 'MusicCatalogManager.exe'))) { throw 'Build the PyInstaller bundle first' }
# Use a fresh staging directory; never remove a previous build or user data.
$Stage = Join-Path $ProjectRoot ('build\msix-stage-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Stage | Out-Null
Copy-Item -LiteralPath $Bundle -Destination $Stage -Recurse
Copy-Item -LiteralPath $ManifestPath -Destination (Join-Path $Stage 'AppxManifest.xml')
& (Join-Path $ProjectRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'make_msix_assets.py') (Join-Path $Stage 'Assets')
if ($LASTEXITCODE -ne 0) { throw 'MSIX asset generation failed' }
$Output = Join-Path $ProjectRoot "dist\MSIX-$Version"
New-Item -ItemType Directory -Path $Output -Force | Out-Null
$BaseName = "MusicCatalogManager-$Version-x64"
$Unsigned = Join-Path $Output "$BaseName-Store-unsigned.msix"
$Signed = Join-Path $Output "$BaseName-Test-signed.msix"
& $MakeAppx pack /o /h SHA256 /d $Stage /p $Unsigned
if ($LASTEXITCODE -ne 0) { throw 'MakeAppx validation/packaging failed' }
Copy-Item -LiteralPath $Unsigned -Destination $Signed -Force
# The private key stays in the Windows certificate store. No PFX is exported.
& $SignTool sign /fd SHA256 /sha1 $Certificate.Thumbprint /s My $Signed
if ($LASTEXITCODE -ne 0) { throw 'MSIX signing failed' }
& $SignTool verify /pa /v $Signed
if ($LASTEXITCODE -ne 0) { throw 'MSIX signature verification failed' }
$PublicCertificate = Join-Path $Output 'MusicCatalogManager-Test-Public.cer'
Export-Certificate -Cert $Certificate -FilePath $PublicCertificate -Force | Out-Null
Copy-Item -LiteralPath $ManifestPath -Destination (Join-Path $Output 'AppxManifest.xml') -Force
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\MSIX.md') -Destination (Join-Path $Output 'README-MSIX.md') -Force
$Artifacts = @($Unsigned, $Signed, $PublicCertificate)
$Hashes = foreach ($Artifact in $Artifacts) { (Get-FileHash -LiteralPath $Artifact -Algorithm SHA256).Hash.ToLower() + '  ' + (Split-Path $Artifact -Leaf) }
$Hashes | Set-Content -LiteralPath (Join-Path $Output 'SHA256SUMS.txt') -Encoding UTF8
@{
    name = $Identity.Name; publisher = $Publisher; version = $Version; architecture = 'x64'
    certificate_thumbprint = $Certificate.Thumbprint; certificate_expires = $Certificate.NotAfter.ToString('o')
    store_id = '9P44BDRDZFJX'; expected_pfn = 'MarekZettel-zetmar.MusicCatalogManager_411qrz2m02jw4'
    unsigned_package = $Unsigned; signed_package = $Signed; stage = $Stage
    sdk = $SdkBin; signature_verified = $true
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Output 'build-result.json') -Encoding UTF8
Write-Output "MSIX packages ready: $Output"
