# Historia zmian

## 0.4.0 — 2026-10-27

- Grupowanie i filtrowanie według playlisty z kolejnością i powtórzeniami wpisów.
- Wyszukiwanie playlist w folderze głównym i podfolderach; wybór plików, opcjonalne skanowanie audio i raport importu.
- Import M3U/M3U8, PLS, WPL, XSPF; względne ścieżki, file URI, UTF-8/UTF-16 i starsze kodowanie Windows.
- Ponowny import aktualizuje listę rozpoznaną po ścieżce źródłowej; niezależne listy o tej samej nazwie nie są nadpisywane.
- Wyszukiwanie okładek po albumie i jego wykonawcy przez MusicBrainz/CAA, podglądy i wybór obrazu; MBID pozostaje opcją zaawansowaną.
- Widoczne polecenie wyboru JPEG/PNG z dysku, również bez internetu.
- Pomoc offline PL/EN w osobnych plikach HTML, menu Pomoc, przełącznik języka i F1.
- Schemat SQLite pozostaje 2.

## 0.3.0 — 2026-10-26

- Cofanie całych edycji zbiorczych, także po ponownym uruchomieniu; migracja SQLite 1 → 2.
- Rejestr kopii oryginalnych plików i przywracanie audio z weryfikacją SHA-256 oraz kopią bezpieczeństwa.
- Filtrowanie i sortowanie w SQLite, asynchroniczne strony po 250 rekordów, opóźnienie wyszukiwania i scalanie zapytań.
- Szybkie filtry, czyszczenie filtrów, wybór kolumn i zapamiętywany układ.
- Przeglądanie albumów z okładkami, widoki folderów i kopii oraz czytelniejsze szczegóły utworu.
- Playlisty z kolejnością i M3U/M3U8; widoczna kolejka, losowanie i powtarzanie utworu lub kolejki.
- Metadane całego albumu z wyborem wydania i podglądem dopasowań; odczyt tagów z nazwy pliku.
- Raport braków i spójności kolekcji, kandydaci podobnych nagrań według tagów i czasu.
- Lokalne porównanie audio (pierwsze 60 sekund, 2–20 utworów), wynik jako sugestia do weryfikacji.
- Poprawione sortowanie statusów, zapis folder.jpg raz na folder i anulowanie zmiany nazw/kopii.
- Modele tabeli i widoki funkcji wydzielone z głównego okna; testy regresji i pomiar 10/50/100 tys. rekordów.

## 0.2.0 — 2026-10-26

- Odtwarzanie lokalnych plików zapisanych w katalogu przez Qt Multimedia.
- Pasek: poprzedni, odtwarzanie/pauza, stop, następny, pozycja i zapamiętywana głośność.
- Dwuklik lub Enter uruchamia zaznaczony utwór; spacja steruje odtwarzaniem w tabeli.
- Kolejka zaznaczonych utworów albo aktualnie widocznej listy, z automatycznym przejściem do następnego.
- Zwalnianie pliku przed zapisem tagów, zmianą nazw, przywróceniem bazy i relinkowaniem.
- Testy dekodowania 8 formatów, błędów, sterowania i współpracy odtwarzania z edycją.

## 0.1.0 — 2026-10-26

- Pierwsza implementacja katalogu SQLite, skanowania w tle, edytora i filtrowania.
- Zapis tagów przez plik tymczasowy z weryfikacją, kopie audio i podgląd zmian nazw.
- Opcjonalne integracje MusicBrainz i Cover Art Archive.
- Sprawdzane kopie ZIP, przywracanie i relinkowanie folderów.
- PL/EN, motywy, oryginalna ikona, skrypty EXE i instalatora.
