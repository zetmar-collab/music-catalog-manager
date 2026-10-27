# Music Catalog Manager 0.3.0 — raport zmian

Data: 26 października 2026. Zmiany wykonano w bieżącym repozytorium. Testy i podglądy używały osobnych profili oraz danych syntetycznych. Nie skanowano ani nie modyfikowano prywatnej kolekcji.

## Etap 1 — cofanie i odzyskiwanie

- SQLite migruje z wersji schematu 1 do 2. Dodatkowa migracja jest transakcyjna i zachowuje wcześniejszą historię.
- Każda nowa edycja ma identyfikator operacji; cofnięcie obejmuje wszystkie jej utwory. Historyczne wpisy bez identyfikatora cofają się pojedynczo. Przycisk podaje liczbę utworów i prosi o zatwierdzenie konkretnego zakresu.
- Rejestr kopii audio przechowuje utwór, pierwotną ścieżkę, kopię, datę i SHA-256. Przywrócenie weryfikuje zawartość i położenie kopii, tworzy kopię zastępowanego pliku, atomowo podmienia audio oraz odświeża tagi i okładkę w katalogu.
- Kopie z 0.2.0 nie mają rejestru; można je przywrócić ręcznie. Kopia ZIP katalogu nadal nie zawiera audio ani plików z audio-backups.

## Etap 2 — biblioteka i wydajność

- Strony po 250 utworów; zapytania filtrów, wyszukiwania i sortowania wykonują się w SQLite poza wątkiem interfejsu.
- Wyszukiwanie czeka 250 ms po ostatnim znaku. Zapytania mają identyfikator generacji; anulowanie przez SQLite progress handler i scalanie żądań zapobiegają zastępowaniu nowych wyników starymi.
- Status ma osobny klucz sortowania; numery utworów i płyt sortują się numerycznie.
- Eksport CSV/JSON działa w tle, obejmuje wszystkie strony filtra, czyta dane partiami i atomowo finalizuje wynik. Anulowanie zachowuje istniejący plik docelowy.
- Zmiana nazw sprawdza anulowanie pomiędzy plikami; anulowana operacja wycofuje wykonane ruchy. Kopie ZIP sprawdzają anulowanie podczas zrzutu SQLite, dodawania plików i weryfikacji; przywracanie sprawdza je do etapu finalizacji.

Pomiar syntetycznej bazy na tym komputerze (pojedyncze przebiegi, bez obietnicy czasu na innym sprzęcie):

| Utwory | Załadowane rekordy | Strona | Wyszukiwanie | Listy filtrów |
|---|---:|---:|---:|---:|
| 10 000 | 250 | 53 ms | 53 ms | 40 ms |
| 50 000 | 250 | 189 ms | 214 ms | 178 ms |
| 100 000 | 250 | 382 ms | 443 ms | 390 ms |

Szczegóły: `library-benchmark.json`. Pomiar dotyczy zapytań katalogu, nie skanowania audio. Szczyt alokacji Pythona podczas pobierania jednej strony wynosił około 350 KiB; nie jest to pomiar całego RAM aplikacji. Budowa pełnej kolejki i część dialogów nadal mogą materializować wyniki i wymagają osobnych pomiarów dla bardzo dużych list.

## Etap 3 — interfejs

- Uproszczony pasek główny; dodatkowe czynności w menu Narzędzia i pod prawym przyciskiem.
- Szybkie filtry, opis aktywnych filtrów, czyszczenie filtrów, wybór kolumn i zapamiętywanie układu, geometrii oraz sortowania.
- Tytuł, wykonawca, album i podstawowe parametry w panelu szczegółów. Informacje techniczne można rozwinąć. Okładka skaluje się z zachowaniem proporcji.
- W kompaktowym oknie ukrywane są nagłówek i dolne przyciski; operacje pozostają w menu. Dodatkowe filtry można rozwinąć. Przy szerokości poniżej 1100 punktów szczegóły są dostępne w osobnym dialogu. Odtwarzacz pozostaje poza przewijanym obszarem biblioteki.
- Osobne widoki albumów, folderów, kopii i playlist; historia w tabeli.
- Natywne podglądy przy skalowaniu 100%, 125% i 200%. Przy 200% Windows zmniejszył wysokość obszaru klienta z zadanych 540 do 531 punktów; odtwarzacz i nawigacja były dostępne. Wyniki: `ui-review.json`.
- Zrzuty: `docs/screenshot.png`, `docs/albums.png`, `docs/compact-200.png`.

## Etap 4 — nowe funkcje

| Funkcja | Realizacja |
|---|---|
| Albumy | Siatka okładek, wyszukiwanie, dwuklik otwierający album z uwzględnieniem wykonawcy albumu i sortowaniem numerów utworów. |
| Playlisty | Trwała kolejność i powtórzenia, odtwarzanie, edycja kolejności przez przeciąganie, usuwanie pozycji, import/eksport M3U/M3U8. |
| Kolejka | Widoczna lista, zmiana kolejności i usuwanie; usunięcie aktualnego utworu zwalnia jego źródło. |
| Odtwarzanie | Losowanie, powtarzanie utworu lub całej kolejki, zapis preferencji. |
| Metadane albumu | Wybór wydania MusicBrainz, dopasowanie według numeru utworu/płyty albo jednoznacznego tytułu, podgląd i zapis do katalogu jako jedna cofana operacja. |
| Tagi z nazwy | Szablony nazwanych pól ze stałymi separatorami, walidacja wszystkich nazw i podgląd zmian. |
| Jakość kolekcji | Brakujące tagi i okładki, niedostępne pliki, warianty pisowni wykonawcy, brakujące i powtórzone numery; eksport JSON. |
| Podobne nagrania | Kandydaci według tytułu, wykonawcy i czasu; niezależny tryb lokalnego porównania początku audio. |
| Okładki folderów | Jeden zapis i jedno potwierdzenie zastąpienia na folder, niezależnie od liczby zaznaczonych utworów. |

Porównanie audio: 2–20 zaznaczonych plików, pierwsze 60 sekund, dekodowanie Qt w workerze, cechy 8 pasm w oknach 0,5 s, normalizacja i podobieństwo kosinusowe z ograniczonym wyrównaniem. To eksperymentalna heurystyka; wynik 100 nie dowodzi identyczności nagrania. Cisza i bardzo krótkie pliki dają komunikat o niewystarczającym materiale. Nic nie jest usuwane automatycznie.

Integracja albumów używa oficjalnego kontraktu MusicBrainz: https://musicbrainz.org/doc/MusicBrainz_API. Testy HTTP korzystają z kontrolowanych odpowiedzi; nie wykonano testu na żywym API z kontaktem autora. Użytkownik nadal konfiguruje prawdziwy kontakt przed włączeniem usług internetowych.

## Etap 5 — architektura i weryfikacja

Nowe moduły UI: `models.py`, `library_views.py`, `widgets.py`. Nowe usługi: `library.py`, `audio_backups.py`, `playlists.py`, `organize.py`, `audio_compare.py`, `export.py`. Pozostawiono Python, PySide6 i SQLite.

**50 testów pytest zaliczonych, bez pominięć.** Raport maszynowy: `pytest.xml`. Obejmuje m.in. migrację z 1, grupowe cofanie po restarcie, przywracanie i odwrócenie przywrócenia audio, uszkodzoną kopię, anulowanie i rollback zmian nazw, stronicowanie, Unicode, walidację sortowania, M3U z powtórzeniami, analizę jakości, QAudioDecoder w workerze, kompletność eksportu i zapis okładki raz na folder. Zachowane testy obejmują odczyt/zapis i dekodowanie ośmiu formatów.

Polecenia:

```powershell
.venv\Scripts\python.exe -m pytest -q --junitxml=reports\pytest.xml
.venv\Scripts\python.exe scripts\benchmark_library.py
.venv\Scripts\python.exe scripts\review_ui.py
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

Testy nie zastępują uruchomienia na czystej maszynie bez Pythona, testów utraty zasilania ani porównania na dużym korpusie różnych masteringów. Nie zmieniono modelu licencji ani podpisywania programu.

## Weryfikacja pakietu Windows

Spakowany EXE uruchomił się na osobnym profilu: wersja 0.3.0, schemat 2, poprawna ikona i polskie etykiety. Dekodowanie dołączonym Qt/FFmpeg zakończyło się poprawnie dla AIFF, FLAC, M4A, MP3, OGG, OPUS, WAV i WMA. To test dekodowania buforów, nie odsłuchu przez fizyczne głośniki. Raporty: `packaged-result.json` i `playback-result.json`.

Instalator 0.3.0 zbudowano przez Inno Setup. Oddzielna instalacja akceptacyjna sprawdziła instalację, skrót, start, ikonę, odinstalowanie i zachowanie katalogu użytkownika. Użyto odrębnego AppId i profilu w build; wynik: `installer-result.json`. To nadal nie jest test na czystej maszynie Windows bez środowiska deweloperskiego.

Gotowe pliki lokalne: `dist/MusicCatalogManager-0.3.0-Setup.exe`, `dist/MusicCatalogManager-0.3.0-portable.zip` i `dist/MusicCatalogManager-0.3.0-source.zip`. Sumy SHA-256: `release-hashes.json`. Nie publikowano wydania w internecie.
