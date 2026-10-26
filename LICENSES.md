# Licencje i źródła — sprawdzono 2026-10-26

Kod Music Catalog Manager jest udostępniony na GPL-3.0-or-later (`LICENSE`). Oryginalny znak nuty i folderu w SVG/ICO jest częścią projektu i ma tę samą licencję. Nie wykorzystuje logotypu MusicBrainz ani Qt.

| Składnik | Wersja testowana | Licencja i źródło |
|---|---|---|
| Python | 3.12.10 | PSF License; https://docs.python.org/3/license.html |
| PySide6-Essentials / shiboken6 / Qt | 6.12.0 | LGPLv3/GPLv3 lub komercyjna; https://doc.qt.io/qtforpython-6/ oraz https://www.qt.io/licensing/ |
| Mutagen | 1.48.1 | GPL-2.0-or-later; https://mutagen.readthedocs.io/en/latest/ |
| HTTPX | 0.28.1 | BSD-3-Clause; https://github.com/encode/httpx/blob/master/LICENSE.md |
| Pillow | 13.0.0 | MIT-CMU i licencje zależności binarnych; https://github.com/python-pillow/Pillow |
| pytest | 9.1.1 | MIT, narzędzie testowe; https://github.com/pytest-dev/pytest |
| PyInstaller | 6.22.3 | GPL-2.0 z wyjątkiem dla budowanych aplikacji oraz części Apache-2.0; https://pyinstaller.org/en/stable/license.html |
| Inno Setup | 6.7.3 | Własna licencja; użycie komercyjne wymaga sprawdzenia aktualnych warunków/licencji; https://jrsoftware.org/isdl.php |
| FFmpeg | Narzędzie lokalne, niepakowane | Licencja zależy od kompilacji; https://ffmpeg.org/legal.html |

Dokładny inwentarz runtime wraz z wersjami i kopiami tekstów licencji pakietów generuje `scripts/collect_licenses.py` do `third_party_licenses`. Dystrybucja zawiera ten katalog. Kod źródłowy projektu i skrypty budowania trzeba udostępniać odbiorcom zgodnie z GPL; sama obecność EXE nie spełnia wszystkich obowiązków. Biblioteki Qt pozostają dynamiczne w pakiecie folderowym. Przy wydaniu sprawdź obowiązki dotyczące źródeł użytych wersji Qt i pozostałych bibliotek, informacji o prawach, wymiany bibliotek i składników Pillow. Nie używamy modułów Qt wymagających wyłącznie GPL, takich jak Charts. Nie przesądza to zgodności dowolnie zmodyfikowanej dystrybucji.

## Usługi i dane

Metadane pochodzą z **MusicBrainz**, grafiki z **Cover Art Archive**. Te oznaczenia są widoczne w interfejsie i wynikach wyszukiwania.

- API MusicBrainz: https://musicbrainz.org/doc/MusicBrainz_API — niekomercyjne użycie usługi jest bezpłatne; komercyjne wymaga kontaktu lub planu komercyjnego. Nie myl warunków API z licencją samych danych.
- Limity: https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting — znaczący User-Agent z nazwą, wersją i kontaktem; aplikacja ogranicza do jednego żądania na 1,05 sekundy, wspólnie dla wątków.
- Dane podstawowe MusicBrainz: CC0. Dane dodatkowe: CC BY-NC-SA 3.0. https://musicbrainz.org/doc/About/Data_License. Wyszukiwarka pobiera podstawowe pola nagrań i wydań; nie pobiera ocen użytkowników ani społecznościowych tagów.
- Cover Art Archive API: https://musicbrainz.org/doc/Cover_Art_Archive/API. Prawa do konkretnych okładek pozostają przy właścicielach; dostęp do API nie daje automatycznie prawa do publikacji grafiki. https://musicbrainz.org/doc/Cover_Art_Archive.
- Dokumentacja Mutagen: https://mutagen.readthedocs.io/en/latest/.

Nie skonfigurowano fikcyjnego kontaktu autora. Przed użyciem API ustaw rzeczywisty kontakt w Ustawieniach. Dane cache są lokalne. Lista muzyki nie jest wysyłana w tle.
