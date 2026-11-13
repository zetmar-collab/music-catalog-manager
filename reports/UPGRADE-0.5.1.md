# Music Catalog Manager 0.5.1 — ciągłe odtwarzanie albumu i folderu

Data: 4 listopada 2026. Wersja MSIX: 1.5.1.0. Schemat SQLite: 2.

## Poprawione zachowanie

Po zmianie widoku na inny album, folder lub playlistę przycisk Odtwórz tworzy kolejkę nowego zakresu. Wcześniej mógł wznowić starą kolejkę zawierającą tylko jeden utwór. Nowa kolejka obejmuje wszystkie strony wyników, uwzględnia aktualne zaznaczenie i pomija zaznaczenie, które nie należy już do nowego widoku. Gdy w nowym widoku nic nie zaznaczono, zaczyna od jego pierwszego utworu.

W tym samym zakresie przycisk zachowuje funkcję pauzy i wznowienia. Samo sortowanie i przejście na inną stronę tabeli nie resetuje istniejącej kolejki. Po ostatnim utworze tryb Bez powtarzania zatrzymuje odtwarzanie; Powtarzaj kolejkę wraca do początku, a Powtarzaj utwór odtwarza bieżące nagranie ponownie.

Obsługa EndOfMedia w Qt zleca przejście przez jednorazowy timer po zakończeniu obsługi sygnału backendu. Spóźnione lub powtórzone zdarzenia nie powinny zmienić utworu po Stop, ręcznej zmianie źródła lub zwolnieniu odtwarzacza: sprawdzana jest generacja i tożsamość odtwarzacza.

## Testy

Pełny zestaw: **80 testów zakończonych powodzeniem**, bez pominięć. Testy odtwarzacza: 13.

Nowe testy obejmują zmianę jednoelementowej kolejki na album i folder przy tabeli stronicowanej po jednym utworze, automatyczne dojście do końca kolejki, powtarzanie utworu i kolejki, dwa kolejne wpisy tego samego pliku, anulowanie przejścia przez Stop oraz nieaktualne zaznaczenie i pusty nowy zakres. Testy ciągłego odtwarzania wykorzystują rzeczywisty dekoder Qt i sztuczne WAV, z wyjściem buforowym niezależnym od fizycznego urządzenia audio. Nie potwierdzają odsłuchu na głośnikach.

Diagnostyka `--verify-playback` sprawdza osiem formatów, a następnie naturalne przejścia przez kolejkę zawierającą dodatkowo powtórzony pierwszy plik. Dzięki temu tę samą kontrolę można wykonać w zamrożonym EXE. Wyniki gotowego pakietu są w `playback-result.json` i `packaged-result.json`.

Gotowy EXE 0.5.1 przeszedł sprawdzenie startu oraz dekodowania AIFF, FLAC, M4A, MP3, OGG, OPUS, WAV i WMA. Ciągła kolejka zakończyła kolejno wpisy 0–8 bez błędów. Instalator przeszedł instalację, uruchomienie, sprawdzenie skrótu i deinstalację z zachowaniem osobnego profilu testowego. Oba MSIX przeszły MakeAppx, kontrolę integralności i porównanie wspólnej zawartości; podpis wersji testowej zweryfikował SignTool. Niepodpisany MSIX nie zawiera podpisu. Wyniki MSIX zapisano w `msix-validation-1.5.1.0.json`.

## Pliki

Instalator `MusicCatalogManager-0.5.1-Setup.exe`, wersja przenośna i źródła są w `dist`. Pakiety MSIX niepodpisany do Store i podpisany do testów są w `dist/MSIX-1.5.1.0`. Testy korzystają z osobnych profili i plików demonstracyjnych. Istniejąca instalacja MSIX 1.5.0.0 nie jest zastępowana przez test akceptacyjny. Samo przygotowanie poprawki nie oznacza przesłania aktualizacji w Partner Center.
