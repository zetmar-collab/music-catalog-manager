# Music Catalog Manager — materiały do Partner Center

Przygotowano: 28 października 2026. Store ID: 9P44BDRDZFJX. Wersja pakietu: 1.5.0.0; aplikacja: 0.5.0.

Status: zgłoszenie 1152921505702251515 wysłano 28 października 2026. Partner Center potwierdził „In certification”, etap „Pre-processing”. Cena: bezpłatna na wszystkich rynkach. Publikacja automatyczna po pozytywnej certyfikacji. Zapisano karty en-US i pl-PL, po dwa zrzuty, politykę prywatności jako tekst i notatki dla certyfikacji.

## Ustawienia zgłoszenia

- Cena: Free / Bezpłatna. Brak wersji próbnej, zakupów w aplikacji, abonamentu i reklam.
- Sugerowana kategoria: Music / Muzyka; wybrać odpowiadającą jej pozycję dostępną w formularzu.
- Logowanie: niewymagane. Internet: opcjonalny, do metadanych i okładek.
- Platforma: Windows Desktop, x64, Windows 10 2004 lub nowszy / Windows 11.
- Języki interfejsu i pomocy: polski, angielski.
- Strona projektu: https://github.com/zetmar-collab/music-catalog-manager
- Adres pomocy: https://github.com/zetmar-collab/music-catalog-manager/issues — zweryfikowano HTTP 200 i zapisano w formularzu.
- Nie zmieniać przesłanego pakietu i wypełnionego formularza klasyfikacji wiekowej.
- Nie deklarować przetestowanej dostępności dla wszystkich technologii asystujących.
- Polityka prywatności: treść z `PRIVACY.txt` została zapisana bezpośrednio w Partner Center, przy użyciu opcji Provide privacy policy text.

## Polski — opis krótki

Uporządkuj muzykę na komputerze: katalog, odtwarzacz, tagi, playlisty i okładki albumów.

## Polski — opis

Music Catalog Manager pomaga uporządkować własną kolekcję muzyki na komputerze. Dodaj foldery z plikami audio, przeszukuj bibliotekę i filtruj utwory według wykonawcy, albumu, gatunku, formatu lub folderu. Grupuj nagrania także według playlisty i słuchaj ich we wbudowanym odtwarzaczu.

Edytuj tagi pojedynczo lub zbiorczo. Importuj playlisty z folderu głównego i podfolderów oraz eksportuj listy M3U. Wyszukuj okładki według wykonawcy i albumu w MusicBrainz i Cover Art Archive albo dodawaj własne obrazy z dysku.

Twórz kopie katalogu i przywracaj zapisane dane. Możesz usunąć z katalogu jeden folder lub wyczyścić całą bibliotekę, pozostawiając pliki muzyczne na dysku. Przed tymi operacjami program tworzy kopię bezpieczeństwa.

Aplikacja jest bezpłatna, nie wymaga konta i zawiera interfejs oraz pomoc po polsku i po angielsku. Katalogowanie i odtwarzanie lokalnej muzyki działają offline. Internet jest potrzebny do opcjonalnego wyszukiwania metadanych i okładek. Program nie dostarcza ani nie pobiera nagrań muzycznych.

Obsługiwane formaty audio: MP3, FLAC, M4A, OGG, OPUS, WAV, WMA i AIFF. Przeznaczona dla Windows 10 w wersji 2004 lub nowszej oraz Windows 11, na komputerach x64.

## Polski — funkcje

- Katalogowanie folderów z muzyką i przeszukiwanie biblioteki.
- Filtrowanie i grupowanie według albumu, wykonawcy, folderu i playlisty.
- Wbudowany odtwarzacz z kolejką, losowaniem i powtarzaniem.
- Edycja tagów pojedynczych utworów i zaznaczonej grupy plików.
- Import M3U, M3U8, PLS, WPL i XSPF, również z podfolderów.
- Wyszukiwanie okładek online oraz dodawanie obrazu z dysku.
- Kopie katalogu oraz usuwanie folderu lub całej biblioteki z kopią bezpieczeństwa.
- Interfejs i pomoc offline w języku polskim i angielskim.

Słowa kluczowe: katalog muzyki; odtwarzacz muzyki; edytor tagów; playlisty; okładki albumów; biblioteka muzyczna; MP3 FLAC.

Informacje o wersji: Usuwanie pojedynczego folderu z katalogu i czyszczenie całej biblioteki z automatyczną kopią bezpieczeństwa. Grupowanie według playlisty, import list z podfolderów, wyszukiwanie okładek oraz pomoc PL/EN.

## English — short description

Organize local music with a searchable catalog, player, tag editor, playlists and album covers.

## English — description

Music Catalog Manager helps you organize your own music collection on your PC. Add folders of audio files, search your library and filter tracks by artist, album, genre, format or folder. Group tracks by playlist and listen using the built-in audio player.

Edit tags individually or in batches. Import playlists from a folder and its subfolders, and export M3U playlists. Find album covers by artist and album using MusicBrainz and Cover Art Archive, or add your own images from disk.

Back up and restore your catalog. Remove one registered folder or clear the entire catalog while keeping your music files on disk. The app creates a safety backup before either removal operation.

The app is free, requires no account, and includes Polish and English interfaces and offline help. Cataloging and local playback work offline. Internet access is needed for optional metadata and cover searches. The app does not provide or download music recordings.

Supported audio formats: MP3, FLAC, M4A, OGG, OPUS, WAV, WMA and AIFF. Requires Windows 10 version 2004 or later, or Windows 11, on an x64 PC.

## English — features

- Catalog music folders and search your local library.
- Filter and group by album, artist, folder and playlist.
- Built-in audio player with queue, shuffle and repeat.
- Edit tags for individual tracks or selected batches.
- Import M3U, M3U8, PLS, WPL and XSPF playlists, including subfolders.
- Search online for album covers or choose an image from disk.
- Catalog backups and safe removal of folders or the entire library.
- Polish and English interface and offline help.

Keywords: music catalog; music player; tag editor; playlists; album covers; music library; MP3 FLAC.

Release notes: Remove a single registered folder or clear the entire catalog with an automatic safety backup. Playlist grouping, recursive playlist import, online cover search and Polish/English help.

## Notes for certification / runFullTrust justification

This is a free, standalone x64 desktop application built with Python and Qt. No account, subscription, purchase or activation key is required. The package version is 1.5.0.0; the application version is 0.5.0.

To test: launch Music Catalog Manager, select Add folder and choose a folder containing your test audio files. Scan the folder, select a track and choose Play. Edit tags in the catalog, then use Write to files to apply changes to the selected audio files. Test only with copies of your audio files. Playlists can be imported from a folder and its subfolders. Offline help is available from Help / F1, with Polish and English versions.

The runFullTrust capability is required because this is a classic desktop application that reads user-selected music folders, plays local audio, edits file metadata, writes album artwork and manages local SQLite catalog backups. It does not require administrator privileges. No broadFileSystemAccess capability is declared.

Local cataloging and playback work offline. Optional metadata and cover search uses MusicBrainz and Cover Art Archive. Cover search can use the built-in project contact URL. Other metadata actions may require a developer contact URL or email in Settings for the MusicBrainz User-Agent; the project URL https://github.com/zetmar-collab/music-catalog-manager can be used. No user login is needed. The app does not download music recordings.

The signed test package was installed, launched through Windows application activation and uninstalled successfully on the development computer. The package family name matched the Partner Center identity. MakeAppx validation and SignTool signature verification passed. A full Windows App Certification Kit run and clean-VM testing have not been completed.

## Przepływ danych — podstawa treści polityki prywatności

Informacje sprawdzone w kodzie wersji 0.5.0, niepotwierdzające spełnienia wszystkich wymagań prawnych:

- Katalog, ścieżki plików, tagi, playlisty, historia edycji, ustawienia, kopie i pamięć podręczna są przechowywane lokalnie.
- Aplikacja nie zawiera integracji reklamowej, analitycznej ani automatycznego wysyłania raportów awarii do autora.
- Wyszukiwanie online wysyła odpowiednie zapytania i identyfikatory nagrań/wydań do MusicBrainz oraz żądania obrazów do Cover Art Archive i usług obsługujących ich pobieranie.
- Dostawcy usług internetowych otrzymują dane typowe dla połączenia HTTP, w tym adres IP i User-Agent z wersją aplikacji. Wpisany w ustawieniach kontakt jest częścią nagłówka User-Agent.
- Pliki audio nie są przesyłane do tych usług przez aplikację.
- Wyczyszczenie biblioteki nie usuwa ustawień, lokalnych plików obrazów ani kopii bezpieczeństwa. Nie należy obiecywać, że usuwa wszystkie dane aplikacji.
- Należy podać rzeczywisty kontakt autora i działający publiczny adres polityki, jeśli formularz tego wymaga. Nie wolno zakładać adresu na podstawie samej domeny.

## Zrzuty ekranu

Wybrane istniejące zrzuty zawierają demonstracyjną kolekcję, bez potrzeby przesyłania prywatnej biblioteki:

- `screenshot.png`, 1400 × 900 — PL: Biblioteka muzyczna i filtrowanie utworów. EN: Music library and track filters.
- `playback.png`, 1400 × 840 — PL: Odtwarzanie lokalnej muzyki. EN: Local music playback.
- `playlist-grouping.png`, 1400 × 900 — PL: Utwory pogrupowane według playlisty. EN: Tracks grouped by playlist.

Przed wysłaniem porównać kadry z opisem i bieżącą wersją aplikacji. Wersje językowe kart mogą korzystać z tych samych zrzutów, ale interfejs na tych obrazach jest polski.
