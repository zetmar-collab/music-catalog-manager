# Architektura

Od wersji 0.2.0 `ui/playback.py` zawiera odtwarzacz Qt Multimedia (`QMediaPlayer` + `QAudioOutput`), inicjalizowany dopiero na żądanie. Odczytuje ścieżki z rekordów SQLite i tworzy kolejkę z zaznaczenia albo aktualnego widoku tabeli. Nie zmienia schematu bazy; głośność jest zwykłym ustawieniem. Podczas zapisu audio, zmiany nazw, relinkowania i przywracania bazy odtwarzacz zostaje wyłączony. Worker czeka na zakończenie usuwania backendu Qt na pętli zdarzeń, aby Windows zwolnił uchwyt pliku. Dekodery nie są wymagane do samego skanowania.

```text
main.py — profil, blokada instancji, start Qt i zamykanie zadań
  └─ ui/window.py — główne okno i operacje edycji
       ├─ ui/models.py — modele tabeli i proxy sortowania SQL
       ├─ ui/library_views.py — asynchroniczne strony, albumy, playlisty i raporty
       ├─ ui/widgets.py — okładka skalowana bez wymuszania szerokości
       ├─ ui/worker.py — QThread, sygnały postępu, Event anulowania
       └─ services/ — skaner, tagi, zmiana nazw, API, obrazy, kopie
            └─ database/store.py — SQLite i historia
```

UI przekazuje do workerów dane wybranych pozycji; worker nigdy nie odwołuje się do widgetów. Każda operacja bazodanowa otwiera własne krótkie połączenie, z kluczami obcymi i transakcją. Anulowanie jest kooperacyjne. Kolejne zadanie można uruchomić dopiero po posprzątaniu poprzedniego workera. Blokada `QLockFile` zapobiega dwóm procesom korzystającym z jednego profilu.

Schemat 2 (migracja z 1 w transakcji): `library_roots → tracks → artwork`, `scan_jobs → library_roots`; osobno `operation_history` z `operation_id`, `settings`, rejestr `audio_backups` i `playlists → playlist_tracks`. Pozycja na playliście jest kluczem, dzięki czemu ten sam utwór może wystąpić wielokrotnie. Ścieżka utworu jest unikalna; identyfikator pliku, skrót SHA-256 i root mają indeksy. Tagi stanowią mały słownik JSON; obrazy są plikami poza SQLite. `dirty` oddziela dane oczekujące w katalogu od tagów zapisanych na dysku. Kolejna wersja schematu wymaga jawnej migracji; nowsze schematy są odrzucane.

Skaner tylko odczytuje audio. Tożsamość na woluminie opiera się na device/inode, rozmiarze i czasie modyfikacji; przy włączonym hashu możliwe jest potwierdzenie przeniesionej kopii. Nieobecne pliki pozostają w katalogu. Junction points są pomijane. Rozszerzone ścieżki Win32 obsługują katalogi dłuższe niż 260 znaków bez zmieniania ustawień systemu.

Zapis tagów: kopia robocza w folderze utworu → Mutagen → ponowny odczyt i porównanie → opcjonalna kopia oryginału → atomowe zastąpienie. Obce pola zostają zachowane. Zmiana nazwy waliduje cały plan przed wykonaniem i aktualizuje SQLite w transakcji; błąd uruchamia odwrócenie wykonanych ruchów. Nie ma gwarancji transakcji obejmującej wiele plików przy utracie zasilania.

MusicBrainz używa blokady procesowej i zegara monotonicznego do wspólnego limitu żądań; cache ma siedmiodniowy TTL. Usługa wymaga rzeczywistego kontaktu autora. Cover Art Archive otrzymuje MBID konkretnego wydania. Wybór wyniku i zatwierdzenie różnic pozostają w UI.

Backup tworzy spójny zrzut przez SQLite Backup API. ZIP ma manifest i skróty; odtwarzanie waliduje kompletność, bezpieczne nazwy, spójność bazy, klucze obce i referencje do obrazów. Przed zamianą powstaje kopia bezpieczeństwa. Audio nie wchodzi do ZIP.

Pakiet ma postać katalogu PyInstaller z dynamicznymi bibliotekami Qt; instalator Inno Setup działa na koncie użytkownika. Budowanie ma ograniczony PATH, aby nie dołączać obcych bibliotek ICU z innych programów. Tabela ładuje do pamięci maksymalnie 250 rekordów jednej strony. `services/library.py` buduje parametryzowane zapytania z zamkniętą listą pól filtrów/sortowania; oblicza też listy wartości filtrów. Zapytania wykonują się w oddzielnym workerze, mają numer generacji i anulowanie przez SQLite progress handler. Szybkie zmiany filtrów są scalane; stare wyniki nie zastępują nowszych. Eksport przechodzi po stronach i finalizuje plik atomowo. Kolejki odtwarzacza i część dialogów nadal mogą materializować więcej rekordów.


## Usługi 0.3.0

- `services/audio_backups.py`: rejestr kopii, SHA-256, ścieżka w profilu, atomowe przywracanie, kopia zastępowanego audio i odświeżenie tagów/okładki.
- `services/playlists.py`: trwała kolejność, powtórzenia, import/eksport UTF-8 M3U. Import nie skanuje nowych ścieżek ani nie pobiera strumieni.
- `services/organize.py`: parser nazw plików, raport jakości i kandydaci podobnych nagrań.
- `services/audio_compare.py`: QAudioDecoder w workerze z własną pętlą zdarzeń, maks. 60 sekund i 20 plików; normalizowane cechy 8 pasm, podobieństwo kosinusowe i ograniczone wyrównanie czasowe. Jest to heurystyka, nie AcoustID/Chromaprint i nie mechanizm automatycznego usuwania.
- `services/export.py`: strumieniowy eksport wyników filtra do CSV/JSON z anulowaniem i plikiem tymczasowym.
- `services/musicbrainz.py`: wyszukiwanie wydań i pobranie listy utworów albumu; ten sam limit żądań, kontakt i cache co wcześniej. Kontrakt: https://musicbrainz.org/doc/MusicBrainz_API.

W API repozytorium `Library.page()` zwraca `(rows, count)`, `Library.all()` jest iteratorem stron, a `Store.edit(..., operation_id=...)` pozwala łączyć części zapisu w jedno cofnięcie. `Store.undo_count()` podaje liczbę utworów ostatniej operacji. Format archiwum kopii pozostaje 1; schemat SQLite ma wersję 2. Przywrócona starsza baza jest migrowana przed ponownym użyciem.


## Rozszerzenia 0.4.0

`services/playlists.py` obsługuje wykrywanie list w drzewie folderów, parsery M3U/PLS/WPL/XSPF i rejestr źródeł w `settings.playlist_imports`. Nie potrzeba migracji bazy. Każda lista jest zapisywana w oddzielnej transakcji. Powtórny import zachowuje jej identyfikator; nowe kolizje nazw dostają sufiksy. Deklaracje XML DTD/ENTITY są odrzucane, plik ma limit 8 MiB. Import folderu opcjonalnie uruchamia istniejący skaner przed dopasowaniem ścieżek.

W widoku playlisty `Library.page()` dołącza `playlist_tracks` i sortuje po `position`, zachowując powtórzenia oraz stronicowanie. `ui/playlist_import.py` prowadzi wybór źródeł i raport; `ui/cover_views.py` formularz wykonawca/album, wybór podglądów i lokalnego obrazu. `services/covers.py` wyszukuje wydania, pobiera podglądy CAA, próbuje release-group przy braku okładki wydania, waliduje obrazy i usuwa powtarzające się podglądy. API: https://musicbrainz.org/doc/Cover_Art_Archive/API.

`ui/help_view.py` wyświetla `resources/help-pl.html` i `resources/help-en.html` w QTextBrowser. Język pomocy można zmienić niezależnie od języka aplikacji. Zasoby są objęte istniejącym pakowaniem resources w setuptools i PyInstaller.
