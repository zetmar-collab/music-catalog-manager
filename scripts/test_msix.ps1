param([string]$PackagePath = '')
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Release = Get-Content -LiteralPath (Join-Path $ProjectRoot 'src\music_catalog_manager\resources\release.json') -Raw | ConvertFrom-Json
if (-not $PackagePath) { $PackagePath = Join-Path $ProjectRoot ("dist\MSIX-$($Release.msix_version)\MusicCatalogManager-$($Release.msix_version)-x64-Test-signed.msix") }
$Name = 'MarekZettel-zetmar.MusicCatalogManager'
$ExpectedPFN = 'MarekZettel-zetmar.MusicCatalogManager_411qrz2m02jw4'
if (Get-AppxPackage -Name $Name) { throw 'The package is already installed. Refusing to replace an existing installation for an acceptance test.' }
$TestProfile = Join-Path $ProjectRoot ('build\msix-acceptance-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $TestProfile | Out-Null
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace MusicCatalogMsixTest {
    [ComImport, Guid("45BA127D-10A8-46EA-8AB7-56EA9078943C")]
    public class ApplicationActivationManager {}
    [ComImport, Guid("2e941141-7f97-4756-ba1d-9decde894a3d"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IApplicationActivationManager {
        [PreserveSig] int ActivateApplication([MarshalAs(UnmanagedType.LPWStr)] string appId,
            [MarshalAs(UnmanagedType.LPWStr)] string arguments, uint options, out uint processId);
        [PreserveSig] int ActivateForFile(IntPtr appId, IntPtr items, IntPtr verb, out uint processId);
        [PreserveSig] int ActivateForProtocol(IntPtr appId, IntPtr items, out uint processId);
    }
    public static class Launcher {
        public static uint Start(string appId, string arguments) {
            var manager = (IApplicationActivationManager)new ApplicationActivationManager();
            uint processId;
            int result = manager.ActivateApplication(appId, arguments, 2, out processId);
            Marshal.ThrowExceptionForHR(result);
            return processId;
        }
    }
}
'@
$Installed = $null
try {
    Add-AppxPackage -Path $PackagePath
    $Installed = Get-AppxPackage -Name $Name
    if (-not $Installed -or $Installed.PackageFamilyName -cne $ExpectedPFN) { throw 'Unexpected package identity after installation' }
    $AppProcessId = [MusicCatalogMsixTest.Launcher]::Start($ExpectedPFN + '!MusicCatalogManager', '--smoke-test --profile "' + $TestProfile + '"')
    $AppProcess = Get-Process -Id $AppProcessId -ErrorAction SilentlyContinue
    if ($AppProcess -and -not $AppProcess.WaitForExit(30000)) { Stop-Process -Id $AppProcessId; throw 'Packaged activation timeout' }
    $Smoke = Get-Content -LiteralPath (Join-Path $TestProfile 'smoke-result.json') -Raw | ConvertFrom-Json
    if (-not $Smoke.window_visible -or -not $Smoke.catalog_cleanup -or $Smoke.version -ne $Release.version) { throw 'Packaged application smoke test failed' }
    $Result = @{
        installed = $true; activation = $true; package_family_name = $Installed.PackageFamilyName
        package_full_name = $Installed.PackageFullName; version = $Installed.Version.ToString()
        profile = $TestProfile; smoke = $Smoke; uninstalled = $false
    }
} finally {
    if ($Installed) { Remove-AppxPackage -Package $Installed.PackageFullName }
}
if (Get-AppxPackage -Name $Name) { throw 'Test package remains installed' }
$Result.uninstalled = $true
$Result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $ProjectRoot 'reports\msix-acceptance.json') -Encoding UTF8
Get-Content -LiteralPath (Join-Path $ProjectRoot 'reports\msix-acceptance.json')
