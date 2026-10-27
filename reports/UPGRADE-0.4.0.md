# Music Catalog Manager 0.4.0 — playlisty, okładki i pomoc

Data: 27 października 2026. Zmiany sprawdzono na odrębnych profilach i syntetycznych plikach; nie modyfikowano prywatnej kolekcji. Schemat bazy pozostaje 2, więc aktualizacja z 0.3.0 nie wymaga migracji.

## Grupowanie według listy odtwarzania

W bibliotece wybierz **Więcej filtrów → Grupuj według → Playlista**, a następnie nazwę listy. Nazwy zawierają liczbę wpisów. Widok zachowuje zapisaną kolejność i powtórzenia utworów, działa ze stronicowaniem i eksportem. Kliknięcie nagłówka pozwala sortować inaczej. Czyszczenie filtrów wraca do całej biblioteki. Lista jest dostępna także przez **Playlisty → Pokaż utwory**.

Repozytorium biblioteki dołącza teraz `playlist_tracks` zamiast korzystać wyłącznie z IN: powtórzenia nie znikają, a pozycja playlisty jest liczbowym kluczem sortowania. Nie zmieniono tabel bazy.

## Import katalogu głównego i podkatalogów

Polecenie **Narzędzia / Playlisty → Importuj playlisty z folderu**:

1. Wybierz folder główny; wykrywanie obejmuje również jego podfoldery i pomija dowiązania/junction points.
2. Zaznacz listy do wczytania. Domyślnie można najpierw skatalogować audio z tego obszaru, aby dopasować nowe pliki.
3. Import zachowuje kolejność i powtórzenia oraz pokazuje raport dopasowanych wpisów, niedopasowanych ścieżek i błędów poszczególnych plików.
4. Powtórny import ścieżki aktualizuje wcześniej zaimportowaną listę. Rejestr źródeł jest w ustawieniach bazy. Usunięcie playlisty czyści jej powiązanie ze źródłem, aby ponownie użyty identyfikator SQLite nie spowodował nadpisania innej listy.

Obsługiwane formaty importu: **M3U, M3U8, PLS, WPL, XSPF**. Eksport pozostaje M3U/M3U8. Parser obsługuje ścieżki względne względem pliku listy, lokalne file URI, UTF-8/BOM, UTF-16 i starsze kodowanie Windows. XML nie dopuszcza DTD/ENTITY. Limit pliku wynosi 8 MiB. Błąd jednej listy nie blokuje pozostałych. Anulowanie zachowuje ukończone importy; pliki poza skanowanym folderem muszą już być w katalogu. Adresy strumieni internetowych są raportowane jako niedopasowane, bez pobierania muzyki.

## Okładki

Nowe widoczne polecenia w panelu szczegółów, menu Narzędzia i menu kontekstowym:

- **Wyszukaj okładkę w internecie**: formularz uzupełnia wykonawcę albumu (zastępczo wykonawcę utworu) i nazwę albumu. Pola są edytowalne; MBID nie jest wymagany.
- Wyniki MusicBrainz + Cover Art Archive pokazują do 8 różnych podglądów z opisem wydania. Przy braku obrazu konkretnego wydania próbowana jest okładka grupy wydań. Powtarzające się obrazy są pomijane. Błędy źródeł są raportowane oddzielnie od braku wyników.
- Po wyborze pozostaje podgląd i wybór miejsca zapisu: cache katalogu, osadzenie w audio z kopią oryginału albo folder.jpg. Nic nie jest automatycznie nadpisywane w plikach.
- **Wybierz obraz z dysku** działa offline: JPEG/PNG, limit 20 MiB i 25 mln pikseli, normalizacja do JPEG i te same miejsca zapisu.

Domyślny kontakt User-Agent dla wyszukiwania okładek wskazuje rzeczywisty adres repozytorium projektu, odczytany z jego konfiguracji Git. Własny kontakt z Ustawień ma pierwszeństwo. Integracje edycji metadanych zachowują wcześniejsze wymaganie ustawienia kontaktu. Wyszukiwanie okładek wysyła wykonawcę i album; nie wysyła audio ani całej biblioteki.

**Próba na żywym API powiodła się:** dla „Miles Davis / Kind of Blue” zwrócono okładkę wydania z 1987 r., US. Wynik jest w `cover-live.json`. Nie gwarantuje to dostępności okładek dla każdej płyty. Dokumentacja API: https://musicbrainz.org/doc/Cover_Art_Archive/API.

## Pomoc PL/EN

Pomoc offline jest dostępna przez **F1** i **Pomoc → Instrukcja użytkownika**. Menu zawiera również bezpośrednio Polski/English; język można przełączyć wewnątrz okna. Osobne pliki HTML są spakowane z aplikacją:

- `src/music_catalog_manager/resources/help-pl.html`
- `src/music_catalog_manager/resources/help-en.html`

Obie instrukcje obejmują pierwsze kroki, filtry/grupowanie, import folderów, kolejkę, okładki, tagi, kopie, narzędzia, ustawienia, skróty i rozwiązywanie problemów. Działają również po otwarciu bezpośrednio w przeglądarce.

## Weryfikacja

**63 testy pytest zaliczone, bez pominięć**; raport: `pytest.xml`. Nowe testy sprawdzają pięć formatów importu, ścieżki i Unicode, kolejność/powtórzenia, reimport i kolizje nazw, ponowne użycie ID, błędy/anulowanie, XML/limit rozmiaru, grupowanie ze stronami, skan przed importem, wyszukiwanie i walidację okładek oraz lokalny obraz i języki pomocy. Kontrolowane odpowiedzi HTTP sprawdzają także brak okładki wydania i fallback do grupy wydań. Próba żywego API jest osobna.

Sprawdzono natywne podglądy nowych okien. Zrzuty w `docs/`: `playlist-grouping.png`, `playlist-import.png`, `cover-search.png`, `cover-results.png`, `help-pl.png`, `help-en.png`. Obrazy w zrzucie wyników są oznaczonymi, syntetycznymi przykładami UI; rzeczywiste wyszukiwanie potwierdza oddzielny raport API.

Nowe moduły: `services/covers.py`, `ui/cover_views.py`, `ui/playlist_import.py`, `ui/help_view.py`. Istniejące usługi playlist i zapytania biblioteki zostały rozszerzone; nie dodano zależności.

Polecenia do odtworzenia:

```powershell
.venv\Scripts\python.exe -m pytest -q --junitxml=reports\pytest.xml
.venv\Scripts\python.exe scripts\review_0_4.py
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

Ograniczenia: import obejmuje lokalne pliki obecne w katalogu; nie pobiera muzyki. Kodowanie starszych list zależy od ustawień systemu. Źródła internetowe mogą nie mieć okładki lub być chwilowo niedostępne. Testy na tym komputerze nie zastępują testu na czystej maszynie Windows bez Pythona.

## Gotowy pakiet Windows

EXE 0.4.0 przeszedł test startu na oddzielnym profilu: poprawny schemat 2, grupowanie playlist, wyszukiwanie okładek oraz oba pliki pomocy (PL/EN) w pakiecie. Dekodowanie 8 formatów zakończyło się poprawnie; nie jest to test odsłuchu przez fizyczne głośniki. Raporty: `packaged-result.json` i `playback-result.json`.

Instalator 0.4.0 przeszedł oddzielny test instalacji, skrótu, startu, ikony, odinstalowania i zachowania profilu. Użyto odrębnego AppId i katalogów testowych; wynik: `installer-result.json`. Gotowe pliki są w `dist/`: instalator, ZIP przenośny i ZIP źródeł 0.4.0. Sumy SHA-256: `release-hashes.json`. Wydanie GitHub: https://github.com/zetmar-collab/music-catalog-manager/releases/tag/v0.4.0. Do wydania dołączono również osobne pliki pomocy PL/EN.
