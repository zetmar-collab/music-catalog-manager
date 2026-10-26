# Architektura

```text
main.py — profil, blokada instancji, start Qt
  └─ ui/window.py — biblioteka, filtry, szczegóły i dialogi
       ├─ ui/worker.py — QThread, sygnały postępu, Event anulowania
       └─ services/ — skaner, tagi, zmiana nazw, API, obrazy, kopie
            └─ database/store.py — SQLite i historia
```

UI przekazuje do workerów dane wybranych pozycji; worker nigdy nie odwołuje się do widgetów. Każda operacja bazodanowa otwiera własne krótkie połączenie, z kluczami obcymi i transakcją. Anulowanie jest kooperacyjne. Kolejne zadanie można uruchomić dopiero po posprzątaniu poprzedniego workera. Blokada `QLockFile` zapobiega dwóm procesom korzystającym z jednego profilu.

Schemat 1: `library_roots → tracks → artwork`, `scan_jobs → library_roots`; osobno `operation_history` i `settings`. Ścieżka utworu jest unikalna; identyfikator pliku, skrót SHA-256 i root mają indeksy. Tagi stanowią mały słownik JSON; obrazy są plikami poza SQLite. `dirty` oddziela dane oczekujące w katalogu od tagów zapisanych na dysku. Kolejna wersja schematu wymaga jawnej migracji; nowsze schematy są odrzucane.

Skaner tylko odczytuje audio. Tożsamość na woluminie opiera się na device/inode, rozmiarze i czasie modyfikacji; przy włączonym hashu możliwe jest potwierdzenie przeniesionej kopii. Nieobecne pliki pozostają w katalogu. Junction points są pomijane. Rozszerzone ścieżki Win32 obsługują katalogi dłuższe niż 260 znaków bez zmieniania ustawień systemu.

Zapis tagów: kopia robocza w folderze utworu → Mutagen → ponowny odczyt i porównanie → opcjonalna kopia oryginału → atomowe zastąpienie. Obce pola zostają zachowane. Zmiana nazwy waliduje cały plan przed wykonaniem i aktualizuje SQLite w transakcji; błąd uruchamia odwrócenie wykonanych ruchów. Nie ma gwarancji transakcji obejmującej wiele plików przy utracie zasilania.

MusicBrainz używa blokady procesowej i zegara monotonicznego do wspólnego limitu żądań; cache ma siedmiodniowy TTL. Usługa wymaga rzeczywistego kontaktu autora. Cover Art Archive otrzymuje MBID konkretnego wydania. Wybór wyniku i zatwierdzenie różnic pozostają w UI.

Backup tworzy spójny zrzut przez SQLite Backup API. ZIP ma manifest i skróty; odtwarzanie waliduje kompletność, bezpieczne nazwy, spójność bazy, klucze obce i referencje do obrazów. Przed zamianą powstaje kopia bezpieczeństwa. Audio nie wchodzi do ZIP.

Pakiet ma postać katalogu PyInstaller z dynamicznymi bibliotekami Qt; instalator Inno Setup działa na koncie użytkownika. Budowanie ma ograniczony PATH, aby nie dołączać obcych bibliotek ICU z innych programów. Obecna tabela jest pamięciowa — stronicowanie SQLite jest przyszłym usprawnieniem dla bardzo dużych kolekcji.
