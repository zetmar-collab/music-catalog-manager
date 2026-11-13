# Wdrożenie audytu — 0.6.0

Zakres: CODE-AUDIT-2026-11-13.md. Baza pozostaje w schemacie 2.
Testy używają osobnych profili i syntetycznych plików audio.

- [x] 1. Bezpieczeństwo przywracania, folderów i okładek
- [x] 2. Metadane, kolejność albumów i bezpieczny eksport CSV
- [x] 3. Zapytania playlist, kopie strumieniowe i skanowanie
- [x] 4. Pomijanie błędów, polecenia kolejki i przywracanie sesji
- [x] 5. Monitorowanie folderów, inteligentne playlisty i wersje importów
- [x] 6. Przenośna kolekcja, retencja kopii i ReplayGain
- [x] 7. Wersjonowanie, CI, dokumentacja PL/EN i weryfikacja wydania

Publikowanie w GitHub i Microsoft Store nie jest częścią tego wdrożenia.

## Potwierdzone wyniki

- Końcowy pełny zestaw: 113 testów, 0 błędów i 0 pominięć (45,07 s).
- Ruff: reguły błędów krytycznych, bez błędów.
- Mypy: cztery nowe usługi, bez błędów; pozostała część aplikacji nie jest jeszcze w pełni typowana.
- Zależności lokalnego środowiska: zgodne.
- Ochrona przed starym EXE: build_msix.ps1 prawidłowo odmówił opakowania poprzedniego pakietu.
- Playlisty: 100 000 wpisów, jedno połączenie SQLite, 2,852 s z tracemalloc, szczyt 56,27 MiB pamięci Pythona, zachowane powtórzenia. Odczyt uruchamiany w workerze.
- Po ostatnich zmianach: dodatkowe przebiegi 46 i 22 testów zakończone poprawnie.
- Gotowy EXE 0.6.0: okno, ikona, pomoc PL/EN, inteligentne playlisty i kopie przenośne potwierdzone w smoke test.
- Test dekodowania ośmiu formatów i ciągłej kolejki w spakowanym EXE: poprawny. Nie potwierdzano odsłuchu fizycznego urządzenia audio.
- Instalator: instalacja, skrót, uruchomienie i odinstalowanie na osobnym AppId; katalog testowy zachowany.
- MSIX 1.6.0.0: niepodpisany do Store i podpisany testowy; MakeAppx, SignTool, CRC archiwów, zgodność EXE, manifestu oraz odcisku źródeł potwierdzone. Używana instalacja Store 1.5.1.0 zachowana.
- 13 pól zapisywalnych jest wspólnych dla Store, kontroli dirty i weryfikacji zapisu.
- Ponowne skanowanie uzupełnia ReplayGain także w niezmienionych plikach starszego katalogu; niezapisane tagi użytkownika są zachowywane.
- Importowane ścieżki playlist dopasowywane są leksykalnie, bez rozwiązywania obcych UNC/symlinków.

## Ograniczenia do testów środowiskowych

- Nie wykonywano testu na prawdziwym odłączanym NAS ani wielogigabajtowej kolekcji audio. Testy korzystają z plików syntetycznych.
- ReplayGain wymaga istniejących tagów i ponownego skanowania starszego katalogu; poziom wyjściowy Qt jest ograniczony do 100%.
- Monitorowanie używa powiadomień i kontroli stanu co 30 s. Przejście po drzewie dużej biblioteki nadal kosztuje operacje dyskowe, wykonywane w tle.
- WACK i aktualizacja Store na czystej maszynie pozostają kontrolami przed publikacją.

## Pliki wydania

- `dist/MusicCatalogManager-0.6.0-Setup.exe`
- `dist/MusicCatalogManager-0.6.0-portable.zip`
- `dist/MusicCatalogManager-0.6.0-source.zip`
- `dist/MSIX-1.6.0.0/MusicCatalogManager-1.6.0.0-x64-Store-unsigned.msix`
- `dist/MSIX-1.6.0.0/MusicCatalogManager-1.6.0.0-x64-Test-signed.msix`
- `dist/SHA256SUMS-0.6.0.txt`

Wyniki maszynowe: `pytest-0.6.0.xml`, `packaged-0.6.0.json`, `playback-0.6.0.json`, `installer-0.6.0.json`, `msix-validation-1.6.0.0.json`, `playlist-benchmark-0.6.0.json` w katalogu `reports`.
