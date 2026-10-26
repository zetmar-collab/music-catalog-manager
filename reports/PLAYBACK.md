# Odtwarzanie — wersja 0.2.0

Dodano odtwarzanie lokalnych plików wskazanych przez rekordy katalogu SQLite. Audio pozostaje na dysku; schemat bazy 1 i dotychczasowa biblioteka są zachowane.

## Działanie

- Dwuklik lub Enter uruchamia wybrany utwór. Spacja w tabeli i przycisk Odtwórz/Pauza sterują bieżącym utworem.
- Pasek zawiera stop, poprzedni/następny, przewijanie, czas i głośność zapisywaną w ustawieniach.
- Kolejka obejmuje wiele zaznaczonych wierszy albo aktualnie widoczną, posortowaną listę. Przechodzi automatycznie do następnego i zatrzymuje się na końcu.
- Brak pliku, uszkodzony plik lub niedostępny backend pokazują komunikat w pasku. Katalogowanie nie wymaga inicjalizacji odtwarzacza.
- Zapis tagów, zmiana nazw, relinkowanie i przywracanie bazy czekają na zwolnienie backendu odtwarzacza. Odtwarzanie jest wtedy zablokowane.

## Zmienione moduły

`ui/playback.py` — odtwarzacz i pasek Qt Multimedia; `ui/window.py` — sterowanie i współpraca z workerami; `main.py`, `diagnostics.py` — diagnostyka EXE; `translations/pl.json` — etykiety; zależności, licencje oraz skrypty budowania i instalatora.

## Weryfikacja

**33/33 testy pytest zaliczone, bez pominiętych.** Zestaw zawiera 7 testów odtwarzania: dekodowanie ośmiu formatów, pauza/wznowienie, przewijanie, głośność, kolejka i jej koniec, brak/uszkodzenie pliku, sygnał dwukliku, zwolnienie pliku przed zapisem tagów oraz uruchomienie diagnostyki z callbacku Qt.

W finalnym EXE wykonano `--verify-playback` dla syntetycznych MP3, FLAC, M4A, OGG/Vorbis, OPUS, WAV, WMA i AIFF. Wszystkie dostarczyły zdekodowane próbki do `QAudioBufferOutput` i osiągnęły EndOfMedia bez błędów. Wyniki: `playback-result.json`. Wyjście było wyciszone — nie potwierdzono odsłuchem fizycznych głośników. Testy nie obejmują DRM i wszystkich wariantów kodeków.

```powershell
.venv\Scripts\python.exe -m pytest -q --junitxml=reports\pytest.xml
dist\MusicCatalogManager\MusicCatalogManager.exe --verify-playback build\acceptance-audio --profile build\playback-final
```

Skrypt budowania automatycznie sprawdza dekodowanie WAV wewnątrz spakowanego EXE, niezależnie od obecności programu FFmpeg CLI. Biblioteki Qt Multimedia i FFmpeg są w pakiecie.

Test instalatora używa tego samego skryptu i plików programu, z flagą `AcceptanceTest`: osobny AppId, folder oraz grupa skrótów chronią zainstalowaną aplikację użytkownika. Sprawdzono instalację, skrót, ikonę, start przy ograniczonym PATH, deinstalację i zachowanie testowej bazy. Wynik: `installer-result.json`. Zwykły instalator 0.2.0 zachowuje AppId z wersji 0.1.0 i aktualizuje istniejącą instalację.

To nadal komputer deweloperski z Windows 11; test czystego Windows bez Pythona oraz testy żywych API pozostają poza potwierdzonym zakresem. Pierwotny raport wersji 0.1.0 znajduje się w `IMPLEMENTATION.md`.

## Naprawione podczas testów

- Asynchroniczny uchwyt FFmpeg na Windows mógł blokować zapis. Worker rozpoczyna mutację po usunięciu poprzedniego odtwarzacza na pętli zdarzeń.
- Diagnostyka wywołana przez timer czekała na deferred deletion w zagnieżdżonej pętli. Usunięto to oczekiwanie i dodano test regresji; finalny test EXE kończy się poprawnie.
- Pauza po automatycznym przejściu do następnego utworu steruje bieżącą pozycją, niezależnie od zaznaczenia w tabeli.
