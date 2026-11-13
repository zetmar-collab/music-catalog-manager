# Music Catalog Manager — MSIX / Microsoft Store

Aplikacja 0.6.0, pakiet **1.6.0.0**, x64. Windows 10 2004 (19041) lub nowszy / Windows 11. Python i Qt są dołączone; użytkownik nie musi ich instalować.

## Pliki

- `MusicCatalogManager-1.6.0.0-x64-Store-unsigned.msix` — do przesłania w sekcji Packages zgłoszenia w Partner Center. Nie zawiera podpisu testowego. Microsoft Store podpisuje pakiet podczas obsługi zgłoszenia.
- `MusicCatalogManager-1.6.0.0-x64-Test-signed.msix` — do lokalnych testów, podpisany istniejącym certyfikatem z magazynu CurrentUser/My.
- `MusicCatalogManager-Test-Public.cer` — wyłącznie publiczny certyfikat do ustanowienia zaufania na komputerze testowym. Klucz prywatny nie jest eksportowany.
- `AppxManifest.xml`, `SHA256SUMS.txt`, `build-result.json` — manifest, sumy plików i wynik budowania.

Oba MSIX mają tę samą tożsamość i zawartość aplikacji. Pakiet testowy może więc aktualizować lub kolidować z instalacją Store tej samej aplikacji; nie instaluj go zamiast używanej wersji bez zachowania kopii katalogu.

## Tożsamość

| Pole | Wartość |
|---|---|
| Name | `MarekZettel-zetmar.MusicCatalogManager` |
| Publisher | `CN=15A53D32-C868-48EE-B700-5DBB5449CA1B` |
| PublisherDisplayName | `Marek Zettel - zetmar` |
| Version | `1.6.0.0` |
| PFN | `MarekZettel-zetmar.MusicCatalogManager_411qrz2m02jw4` |
| Store ID | `9P44BDRDZFJX` |
| App ID | `MusicCatalogManager` |
| AUMID | `MarekZettel-zetmar.MusicCatalogManager_411qrz2m02jw4!MusicCatalogManager` |

Pierwszy człon wersji pakietu jest większy od zera, a czwarty wynosi zero, zgodnie z wymaganiami numerowania Store. Wersja aplikacji w jej interfejsie nadal wynosi 0.6.0. Przed kolejnym zgłoszeniem ustaw numer wyższy od wcześniej przesłanych pakietów. Końcowe spacje z przekazanych danych zostały usunięte. PFN i SID są wyliczane przez Windows, nie wpisuje się ich jako oddzielnych pól manifestu. Adres opublikowanej karty i deep link należy potwierdzić po uruchomieniu produktu w Store.

## Instalacja testowa

Na tym komputerze pasujący certyfikat jest już zaufany. Otwórz PowerShell w folderze pakietów:

```powershell
Add-AppxPackage -Path .\MusicCatalogManager-1.6.0.0-x64-Test-signed.msix
```

Uruchom aplikację z menu Start. Na innym komputerze testowym najpierw zaufaj publicznemu certyfikatowi — PowerShell jako administrator:

```powershell
Import-Certificate -FilePath .\MusicCatalogManager-Test-Public.cer -CertStoreLocation Cert:\LocalMachine\TrustedPeople
```

Zweryfikowany odcisk SHA-1 certyfikatu: `5047763DCF5DB77675453898888D521F3FED424D`. Temat odpowiada Publisher; ważność do 20 sierpnia 2029. Podpis używa SHA-256 i nie ma znacznika czasu; jest przeznaczony do testów. Wersja Store nie korzysta z tego certyfikatu.

MSIX zarządza własnymi danymi aplikacji i może przekierowywać AppData. Nie zakładaj automatycznej migracji profilu z instalatora EXE. Do przenoszenia katalogu użyj istniejącej funkcji tworzenia i przywracania kopii ZIP. Deinstalacja MSIX może usuwać dane należące do pakietu.

## Budowanie i weryfikacja

Z katalogu repozytorium, po przygotowaniu bieżącego folderu PyInstaller `dist/MusicCatalogManager`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_msix.ps1
powershell -ExecutionPolicy Bypass -File scripts\test_msix.ps1
```

Skrypt budujący używa Windows SDK 10.0.26100.0, tworzy grafiki z istniejącej ikony SVG i wywołuje MakeAppx z walidacją (bez `/nv`). Certyfikat musi mieć zgodny temat, ważność, zastosowanie Code Signing i klucz prywatny. Domyślnie wybierany jest pasujący certyfikat o najdłuższej ważności. Parametr `-CertificateThumbprint` pozwala wskazać konkretny certyfikat. SignTool weryfikuje wynik podpisywania. Nie powstaje PFX ani plik zawierający klucz prywatny.

Test akceptacyjny odmawia zastąpienia istniejącej instalacji. Instaluje podpisany MSIX, sprawdza PFN, uruchamia aplikację przez IApplicationActivationManager z osobnym profilem, sprawdza wynik i usuwa wyłącznie testową instalację.

Dla 1.6.0.0 potwierdzono walidację MakeAppx, integralność ZIP, zgodność zawartości obu pakietów i podpis SignTool. Gotowy EXE 0.6.0 przeszedł również ciągłą kolejkę dziewięciu wpisów w ośmiu formatach audio. Test instalacji, aktywacji i deinstalacji potwierdzono wcześniej dla 1.5.0.0. Test akceptacyjny odmawia zastąpienia istniejącej instalacji; przy zainstalowanej 1.5.0.0 nie uruchamiano go dla 1.6.0.0. PFN pozostaje zgodny z podanym przez Partner Center. Pełny Windows App Certification Kit (WACK) nie był uruchamiany — wymaga sesji z uprawnieniami administratora. Przed wysłaniem można wykonać:

```powershell
$appcert = "${env:ProgramFiles(x86)}\Windows Kits\10\App Certification Kit\appcert.exe"
& $appcert reset
& $appcert test -appxpackagepath "C:\pelna\sciezka\MusicCatalogManager-1.6.0.0-x64-Test-signed.msix" -reportoutputpath "C:\pelna\sciezka\wack-result.xml"
```

Pakiet deklaruje `runFullTrust`, ponieważ zawiera klasyczną aplikację Qt/Python obsługującą wybrane przez użytkownika foldery i zapis tagów w plikach audio. Nie wymaga uruchamiania jako administrator. W Partner Center uzasadnij tę funkcjonalność, jeśli formularz poprosi o opis restricted capability. Pakiet MSIX nie zastępuje opisu produktu, zrzutów ekranu, klasyfikacji wiekowej i pozostałych pól zgłoszenia. Nie wykonano publikacji ani certyfikacji w Partner Center.

Źródła: [ręczne tworzenie pakietu](https://learn.microsoft.com/en-us/windows/msix/desktop/desktop-to-uwp-manual-conversion), [podpisywanie i Microsoft Store](https://learn.microsoft.com/en-us/windows/msix/package/sign-msix-package-guide), [wymagania pakietów i wersji](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/package-version-numbering?pivots=store-installer-msix), [Windows App Certification Kit](https://learn.microsoft.com/en-us/windows/uwp/debug-test-perf/windows-app-certification-kit).
