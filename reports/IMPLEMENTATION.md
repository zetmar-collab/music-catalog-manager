# Raport wykonania — 2026-10-26

Wersja 0.1.0. Windows 11 x64, Python 3.12.10. Projekt uruchomiono, spakowano przez PyInstaller i zbudowano instalator Inno Setup 6.7.3. Weryfikację wykonano na plikach syntetycznych i osobnych profilach. Prywatna kolekcja użytkownika nie była skanowana ani modyfikowana.

**Końcowy wynik: 26 testów pytest zaliczonych, bez pominiętych.** Raport: `pytest.xml`. Osobny test spakowanego programu: `packaged-result.json`. Instalacja, skrót, uruchomienie, ikona i deinstalacja: `installer-result.json`. Zrzut końcowego EXE: `app-final-pl.png`.

Nie jest to pełna akceptacja produkcyjna wszystkich wymagań: nie wykonano uruchomienia w czystej maszynie Windows bez Pythona ani testu z żywym MusicBrainz/CAA z rzeczywistym kontaktem autora. Szczegóły poniżej.

## Etap 1 — szkielet

Pliki: `pyproject.toml`, `main.py`, `database/store.py`, `ui/window.py`, `ui/i18n.py`, `translations/pl.json`, `translations/qtbase_pl.qm`, `resources/icon.svg`, `resources/icon.ico`.

Uruchomienie: `.venv\Scripts\python.exe -m music_catalog_manager.main --profile build\demo\profile`.

Testy: `python -m pytest tests/test_store.py tests/test_ui.py -q` — **3 zaliczone**. Schemat SQLite, klucze obce, ustawienia po ponownym otwarciu, cofanie edycji, PL/EN, polskie standardowe przyciski Qt, trzy motywy i pokazanie okna. Początkowy błąd pustych etykiet EN usunięto.

Ograniczenia: systemowe okna plikowe korzystają z języka Windows; szczegóły techniczne wyjątków bibliotek pozostają w oryginalnym języku.

## Etap 2 — skanowanie

Pliki: `services/scanner.py`, `services/metadata.py`, `ui/worker.py`, `paths.py`, `tests/conftest.py`, `tests/test_scanner.py`.

Testy: `python -m pytest tests/test_scanner.py -q` — **4 zaliczone**. Rekurencja, osiem formatów (MP3, FLAC, M4A, OGG, OPUS, WAV, WMA, AIFF), uszkodzony plik, ponowny skan, przeniesienie, niedostępna lokalizacja, anulowanie, zachowanie edycji w bazie, polskie znaki, ścieżka >260 znaków i rzeczywista pętla junction na Windows.

Ograniczenia: odłączony dysk symulowano zmianą nazwy katalogu, nie fizycznym odłączeniem nośnika. Nie testowano każdego wariantu kontenera MP4 ani udziałów sieciowych.

## Etap 3 — biblioteka

Pliki: modele i filtr w `ui/window.py`, `tests/test_library.py`.

Testy: `python -m pytest tests/test_library.py -q` — **1 zaliczony**, obejmuje wyszukiwanie Unicode bez rozróżniania wielkości liter, filtry, sortowanie czasu i potwierdzone duplikaty SHA-256. Sprawdzono zrzut rzeczywistego okna EXE na przykładowej bibliotece.

Ograniczenia: katalog jest ładowany do pamięci; brak pomiaru dla bardzo dużej kolekcji. Grupowanie to selektor grupy i sortowanie, nie rozwijane drzewo.

## Etap 4 — edycja

Pliki: `services/metadata.py`, `services/rename.py`, `services/artwork.py`, edytor i podglądy w `ui/window.py`, `tests/test_editing.py`.

Testy: `python -m pytest tests/test_editing.py -q` — **9 zaliczonych**. Rzeczywisty zapis i odczyt tagów oraz obrazów w siedmiu formatach, zachowanie obcych tagów, identyfikatory MusicBrainz/ISRC, kopie oryginałów, brak nadpisania folder.jpg, uszkodzony obraz, zablokowany WMA, symulowany błąd zapisu, nazwy zastrzeżone, kolizje oraz rollback zmiany nazw po błędzie.

Ograniczenia: zapis WMA celowo wyłączony; cofnięcie bazy nie cofa audio. Zestaw wielu zapisów nie jest atomowy jako całość. Po awarii procesu podczas zmiany nazw należy ponowić skan. Testowane pliki były małe i sztuczne.

## Etap 5 — integracje

Pliki: `services/musicbrainz.py`, `services/artwork.py`, dialogi wyboru i podglądu, `tests/test_musicbrainz.py`, `LICENSES.md`.

Testy: `python -m pytest tests/test_musicbrainz.py -q` — **4 zaliczone**. Kandydaci nagrań i wydań, MBID wydania, cache, 404 okładki, odpowiedź obrazu, 503, timeout, anulowanie i obowiązkowy kontakt. Dwa równoległe klienty z kontrolowanym transportem wykazały odstęp rzeczywistych wywołań co najmniej 1 sekundy. Wyszukiwanie nie modyfikuje wejściowych tagów.

Aktualne dokumenty MusicBrainz, limity, CAA, Mutagen i licencje sprawdzono online. Jedno pierwsze otwarcie dokumentacji API zwróciło 429; treść warunków zweryfikowano przez oficjalny wynik wyszukiwania i pozostałe strony MusicBrainz.

Ograniczenia: testy korzystają z `httpx.MockTransport`. Nie wykonano testu pobrania z żywej usługi z kontaktem autora — nie podano takiego kontaktu i nie wymyślano go. Użytkownik ustawia rzeczywisty kontakt w Ustawieniach. Przed komercyjną dystrybucją trzeba rozstrzygnąć warunki API i prawa do okładek.

## Etap 6 — kopie

Pliki: `services/backup.py`, `tests/test_backup.py`, dialogi kopii i relinkowania.

Testy: `python -m pytest tests/test_backup.py -q` — **2 zaliczone**. SQLite Backup API, SHA-256, rzeczywiste odtworzenie do osobnego profilu, ustawienia, wpisy, obrazy, indeksy, klucze obce, kopia bezpieczeństwa, relinkowanie, zakaz zastąpienia istniejącego ZIP, odrzucenie Zip Slip i uszkodzonej sumy. Naprawiono wykrytą na Windows blokadę pliku przez niedomknięte połączenie snapshotu.

Ograniczenia: brak pełnej kopii audio, zgodnie z opcjonalnym charakterem tego trybu. Spójność zrzutu bazy jest zapewniona przez Backup API; nie jest to kopia całego dysku.

## Etap 7 — wydanie

Pliki: `MusicCatalogManager.spec`, `scripts/build_windows.ps1`, `scripts/installer.iss`, `scripts/test_installer.ps1`, `scripts/collect_licenses.py`, `scripts/package_sources.py`, `scripts/make_icon.py`, `diagnostics.py`, `README.md`, `ARCHITECTURE.md`, `LICENSE`, `LICENSES.md`, `CHANGELOG.md`.

Testy responsywności i kolejkowania: `python -m pytest tests/test_worker.py -q` — **3 zaliczone**, w tym rzeczywiste skanowanie z okna Qt, anulowanie i dokończenie ponownym skanem. Pełny zestaw: **26/26**.

Polecenie budowania:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1 -InnoCompiler .\tools\InnoSetup\ISCC.exe
```

Zbudowano i uruchomiono `dist/MusicCatalogManager/MusicCatalogManager.exe`. Test wewnątrz EXE przeskanował osiem formatów, zapisał tag i obraz w siedmiu, odtworzył kopię i potwierdził brak zmian oryginalnych danych wejściowych. Zbudowano `dist/MusicCatalogManager-0.1.0-Setup.exe`. Instalator zainstalował program w osobnym katalogu testowym; sprawdzono skrót Start Menu i ikonę, uruchomiono program przy PATH ograniczonym do katalogów Windows, wykonano deinstalację i potwierdzono zachowanie testowego katalogu biblioteki. Testowe zainstalowane pliki i skrót usunięto przez deinstalator.

Pierwszy test EXE wykrył obce ICU z Popplera w PATH. Poprawiono konfigurację pakowania i powtórzono testy z sukcesem. Pierwszy test instalatora szukał skrótu w błędnej grupie; sprawdzono rzeczywistą rejestrację i poprawiono test, bez zmiany instalatora.

Ograniczenia: to komputer deweloperski, nie czysty Windows bez Pythona. Program i instalator nie są podpisane certyfikatem. Brak testu utraty zasilania i macierzy Windows 10/11. Kryterium akceptacyjne 14 pozostaje **niezweryfikowane w wymaganym środowisku**; kryteria usług online są zweryfikowane kontrolowanym transportem, nie żywym serwerem. Nie należy ogłaszać pełnej akceptacji produkcyjnej na podstawie tego raportu.

## Artefakty

- `dist/MusicCatalogManager/` — kompletny folder aplikacji przenośnej.
- `dist/MusicCatalogManager-0.1.0-Setup.exe` — instalator.
- `dist/MusicCatalogManager-0.1.0-portable.zip` — archiwum folderu aplikacji.
- `dist/MusicCatalogManager-0.1.0-source.zip` — źródła, testy, zasoby, licencje i instrukcje budowania.
- `reports/pytest.xml`, `reports/packaged-result.json`, `reports/installer-result.json` — dowody testów.

Warunki użycia i źródła dokumentacji są podane z odnośnikami w `LICENSES.md`. Nie publikowano projektu, nie tworzono kont ani nie wysyłano danych kolekcji do usług zewnętrznych.
