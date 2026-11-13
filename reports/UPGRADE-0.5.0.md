# Music Catalog Manager 0.5.0 — usuwanie danych katalogu

Data: 27 października 2026. Operacje sprawdzono na osobnych profilach i syntetycznych plikach. Nie czyszczono prywatnej biblioteki. Schemat SQLite pozostaje 2.

## Dostępne funkcje

- **Narzędzia → Wyczyść całą bibliotekę** usuwa zapisane utwory, foldery, playlisty, powiązania okładek, historię, zadania skanowania, rejestr kopii audio i rejestr importowanych playlist. Zachowuje język, motyw i pozostałe preferencje programu.
- **Foldery → wybierz folder → Usuń folder z katalogu** usuwa wybrany wpis folderu, przypisane mu utwory i ich powiązania, historię oraz wpisy rejestru kopii audio. Pozostałe foldery i definicje playlist zostają; z playlist znikają tylko wpisy usuniętych utworów. Zakres zależy od przypisanego folderu w bazie, również przy zagnieżdżonych ścieżkach.

Obie operacje pokazują zakres i wymagają potwierdzenia. Nie kasują plików muzycznych, folderów, folder.jpg, obrazów w pamięci podręcznej ani plików kopii oryginalnego audio.

## Bezpieczeństwo i przywracanie

Przed usunięciem powstaje pełna kopia katalogu w folderze profilu: `before-clear-library-*.zip` albo `before-remove-folder-*.zip`. Błąd tworzenia kopii blokuje usuwanie. Kasowanie rekordów jest jedną transakcją SQLite; błąd lub anulowanie przed jej zatwierdzeniem wycofuje zmiany. Operacja zwalnia źródło odtwarzacza, opróżnia kolejkę i odświeża widok oraz filtry.

Aby odzyskać dane, wybierz **Kopie zapasowe → Przywróć kopię katalogu** i wskaż automatyczny ZIP. Przywrócenie zastępuje bieżący katalog stanem kopii. Folder można też ponownie dodać i przeskanować, ale sam skan nie odtworzy wcześniejszych playlist ani niezapisanych zmian tagów.

## Weryfikacja

Pełny zestaw: **74 testy zakończone powodzeniem** (w tym 11 testów nowych funkcji).

Gotowy pakiet EXE 0.5.0 uruchomił okno, załadował ikonę, pomoc PL/EN i obie funkcje usuwania. Test dekodowania i zakończenia odtwarzania przeszedł dla AIFF, FLAC, M4A, MP3, OGG, OPUS, WAV i WMA; nie potwierdza on odsłuchu na fizycznym wyjściu audio. Test instalatora potwierdził instalację, skrót, uruchomienie, ikonę i deinstalację z zachowaniem profilu testowego. Przygotowano instalator, przenośny ZIP, źródła, pomoc PL/EN i sumy SHA-256 w lokalnym folderze `dist`.

Testy nowej usługi obejmują usunięcie jednego folderu, pełne czyszczenie i odtworzenie kopii, zachowanie ustawień i bajtów plików, błąd kopii, nieistniejący folder, anulowanie przed oraz w trakcie kasowania, rollback po błędzie SQL i ponowne użycie identyfikatora utworu bez starej historii cofania. Testy interfejsu obejmują odmowę potwierdzenia i pełny przebieg z resetem kolejki oraz filtrów.

Wyniki pełnego zestawu znajdują się w `pytest.xml`, uruchomienia pakietu w `packaged-result.json`, odtwarzania w `playback-result.json`, instalacji i deinstalacji w `installer-result.json`. Test instalatora używa osobnego identyfikatora aplikacji i osobnego profilu. Test na czystej maszynie Windows lub VM nadal nie został wykonany.
