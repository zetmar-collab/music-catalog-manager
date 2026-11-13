# Music Catalog Manager 0.6.0 — PL

1. Z menu **Narzędzia** lub menu kontekstowego wybierz **Odtwórz album**, **Odtwórz folder**, **Dodaj do kolejki** albo **Odtwórz jako następny**. Polecenia albumu uwzględniają wykonawcę albumu oraz kolejność płyta/utwór. Albumy i zarejestrowane foldery mają również własne przyciski odtwarzania.
2. W **Ustawieniach** włącz **Pomijaj brakujące i uszkodzone utwory**. Lista **Narzędzia → Pominięte utwory** zawiera powody i przycisk ponowienia. Wszystkie niedostępne pozycje kończą próbę; powtarzanie nie powoduje nieskończonej pętli.
3. Program zapamiętuje kolejkę, bieżącą pozycję, tryb powtarzania, losowanie i widok. Po otwarciu kliknij **Odtwórz**. Opcję automatycznego startu można włączyć w ustawieniach. Sesja jest przypisana do profilu.
4. **Monitoruj foldery z muzyką** jest domyślnie wyłączone. Po włączeniu pierwszy przebieg uzgadnia zawartość, a następne skanują zmienione poddrzewa. Powiadomienia systemowe są scalane; kontrola co 30 sekund wykrywa także pominięte powiadomienia i powrót dysku. Błędy dostępu trafiają do historii. Duża kolekcja może wymagać czasu na kontrolę stanu.
5. **Narzędzia → Inteligentne playlisty → Nowa**: podaj nazwę, wybierz wszystkie/dowolną regułę i do 20 warunków. Przykład: gatunek równa się Jazz oraz format równa się FLAC. Pole okładka/jest puste wybiera brakujące obrazy. Wyniki aktualizują się po zmianie katalogu. Listy są oznaczone ★ w grupowaniu playlist.
6. Import pojedynczego pliku lub folderu pokazuje dodane, usuwane i niedopasowane wpisy przed zastosowaniem. Opcja zachowania wcześniejszych wpisów działa również dla powtórzeń. **Poprzednie wersje playlist** przechowują ostatnich 10 wersji każdej aktualizowanej listy; przy przywracaniu pomijane są utwory usunięte już z katalogu. Anulowanie importu wielu list zachowuje listy ukończone wcześniej; pojedyncza lista jest zapisywana transakcyjnie.
7. **Przenośna kopia kolekcji** zawiera katalog, używane okładki i dostępne pliki audio. Brakujące pliki są wymienione w manifeście. Odtwarzanie kopii wymaga nowego folderu i miejsca na całą rozpakowaną kolekcję; nie zastępuje bieżącej biblioteki. Ścieżki są przeliczane, a przywrócony profil można otworzyć w osobnym oknie. Historyczne kopie oryginalnego audio nie są dołączane; ich odnośniki i rejestr lokalizacji importów nie są przenoszone.
8. **Przechowywanie kopii** proponuje usunięcie starszych zwykłych kopii ZIP w profilu po zachowaniu wybranej liczby najnowszych. Pokazuje dokładną listę i wymaga potwierdzenia. Automatyczne kopie `before-*` są chronione; archiwa poza profilem nie są usuwane.
9. **ReplayGain**: wyłączone/utwór/album. Odczytuje istniejące standardowe tagi podczas skanowania; po aktualizacji przeskanuj pliki ponownie, aby uzupełnić wartości w dotychczasowym katalogu. Tryb albumu korzysta z danych utworu, jeśli brak albumowych. Szczyt ogranicza wzmocnienie; Qt ogranicza końcowy poziom do 100%. Program nie wylicza nowych tagów ReplayGain i nie zmienia audio. Brak lub nieprawidłowe wartości oznaczają zwykłą głośność.

CSV zabezpiecza komórki przed interpretacją jako formuły przez dodanie apostrofu do niebezpiecznych prefiksów. **JSON** zachowuje oryginalne wartości do wymiany danych. Zagnieżdżone foldery mają stałą własność: plik należy do najgłębszego zarejestrowanego folderu. Usunięcie rodzica z katalogu zachowuje osobno zarejestrowane dziecko.

# Music Catalog Manager 0.6.0 — EN

Use **Tools** or the track context menu to play an album/folder, append a selection, or play it next. Albums use album artist identity and numeric disc/track order. Album and folder browsers offer the same queue controls.

Settings optionally enable skipping missing/corrupt files, automatic playback of a restored session, folder monitoring, and ReplayGain. All four are off by default. **Skipped tracks** lists reasons and provides Retry. A queue containing only bad files stops even with repeat enabled. Queue order, current position, repeat/shuffle, and library view are remembered per profile; press Play after reopening.

**Smart playlists** provides a visual editor for up to 20 all/any rules. Changes in catalog metadata update membership dynamically. The artwork/empty condition finds tracks without covers. Smart lists appear with a ★ in playlist grouping.

Playlist import previews additions, removals and unmatched paths, optionally retaining old entries and duplicates. **Playlist revisions** restores the last ten saved versions per updated playlist. Deleted catalog tracks are excluded when reverting. Each list is applied transactionally; cancelling a batch preserves already completed lists.

Folder monitoring first reconciles the registered folders, then scans changed subtrees. Coalesced filesystem notifications are supplemented by a background state check every 30 seconds. This also detects missed notifications and returning drives; large libraries take time to check. Access errors appear in History.

**Portable collection backup** streams catalog, referenced artwork and available audio into a hashed ZIP. Missing files are recorded. Restore always creates a new directory, checks free space and file hashes, remaps paths and can open the new profile in a separate window. Original-audio backup history and source import locations are not transferred. Existing music and the current profile are preserved.

**Backup retention** previews older ordinary profile ZIPs beyond the chosen count. Deletion requires confirmation; `before-*` safety backups and files outside the profile are protected.

ReplayGain uses existing standard tags read during scanning; rescan an older catalog to populate these values. Album mode falls back to track tags. Peak values limit gain, and Qt caps final output at 100%. Missing/invalid tags use ordinary volume. No audio analysis, tag writing or sample modification is performed.

Spreadsheet CSV adds an apostrophe to dangerous cell prefixes; JSON preserves raw metadata for interchange. The deepest registered ancestor owns a track, so removing a parent catalog folder preserves a separately registered child.
