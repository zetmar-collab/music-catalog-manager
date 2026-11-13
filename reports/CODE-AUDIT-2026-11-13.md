# Audyt Music Catalog Manager 0.5.1

Data: 13 listopada 2026. Pakiet MSIX: 1.5.1.0. Audyt wykonano według skilla `code-audit`.

## 1. Podsumowanie

Aplikacja kataloguje lokalną muzykę, odtwarza kolejki, edytuje tagi i okładki, importuje playlisty oraz tworzy kopie SQLite i obrazów. Stos: Python 3.12, PySide6/Qt, Mutagen, SQLite, HTTPX i Pillow. Punkt startowy: `src/music_catalog_manager/main.py`; dane: `database/store.py`; budowanie: PyInstaller, Inno Setup i MakeAppx/SignTool.

Ogólny stan: aplikacja ma działający zestaw testów i sensowne zabezpieczenia pojedynczych zapisów audio, ale wymaga wzmocnienia spójności katalogu i przywracania kopii. Nie potwierdzono błędu klasy **Krytyczny** ani wykonania zdalnego kodu. Potwierdzono dwa problemy o **wysokiej** ważności oraz dalsze błędy średniej ważności.

Przejrzano warstwy danych, plików, skanowania, odtwarzacza, importu, integracji sieciowych, interfejsu i dystrybucji. Priorytet otrzymały również lokalne zmiany 0.5.0–0.5.1, których nadal nie zapisano w Git. Audyt dotyczy bieżącego katalogu roboczego, nie tylko ostatniego commita ani stanu GitHub.

Weryfikacja:

- **80 testów przeszło**, bez błędów i pominięć; czas 86,09 s. Osobny raport: `build/audit-2026-11-13-pytest.xml`.
- Sprawdzono składnię **45 plików Python** przez AST.
- `uv pip check`: **25 pakietów zgodnych ze sobą**. Nie jest to kontrola podatności CVE.
- Ruff, mypy, pip-audit i narzędzia pomiaru pokrycia nie są zainstalowane w środowisku projektu; projekt nie konfiguruje lintowania ani type checkera. Nie instalowano ich podczas audytu. `pip` nie występuje w lokalnym venv, dlatego zgodność pakietów sprawdzono przez dostępne `uv`.
- Dodatkowe próby na tymczasowych profilach potwierdziły siedem błędów opisanych w sekcjach 2–3 oraz problem N+1. Dowody: `build/audit-2026-11-13/reproductions.json` i `playlist-query-count.json`.
- Nie zmieniono kodu aplikacji, testów, schematu prywatnej bazy ani instalacji. Utworzono jedynie materiały audytu i dane tymczasowe. Nie wykonano publikacji.

## 2. Błędy krytyczne

Poniższa lista obejmuje błędy funkcjonalne o wysokiej i średniej ważności. Nazwa sekcji nie oznacza, że każdy z nich ma klasę Krytyczny.

### B1. Przywracanie może zastąpić działającą bazę nieprawidłowym schematem

- **Ważność: Wysoki. Potwierdzony.**
- Lokalizacja: [backup.py:113](C:/Users/Marek/Codex/Katalog/src/music_catalog_manager/services/backup.py:113), [backup.py:123](C:/Users/Marek/Codex/Katalog/src/music_catalog_manager/services/backup.py:123).
- Problem: walidacja sprawdza nazwy tabel, integralność i klucze obce, ale nie wymagane kolumny ani pełną strukturę schematu. Podmiana aktywnej bazy następuje przed `migrate()` i `mark_availability()`.
- Dowód: przygotowano archiwum z poprawnymi sumami i bazą wersji 2, w której kolumnę `tracks.path` przemianowano. Przywracanie zastąpiło aktywną bazę, po czym zakończyło się `OperationalError: no such column: path`. Ustawienie starego profilu zniknęło. Kopia bezpieczeństwa powstała, więc dane są możliwe do odzyskania, ale aktywny profil pozostaje niesprawny.
- Wpływ: nieudane przywracanie może uniemożliwić uruchomienie lub używanie katalogu. Suma SHA-256 potwierdza zgodność plików z manifestem, a nie poprawność ani zaufane pochodzenie schematu.
- Minimalna poprawka: sprawdzać kolumny i ograniczenia dla konkretnej wersji, odrzucać nieoczekiwane triggery/widoki, migrować i aktualizować dostępność **w bazie tymczasowej**, a dopiero w pełni przygotowany plik podmieniać atomowo. Awaria przygotowania ma pozostawiać aktywną bazę bez zmian.

### B2. Kolejność skanowania zmienia właściciela utworów w zagnieżdżonych folderach

- **Ważność: Wysoki. Potwierdzony.**
- Lokalizacja: [scanner.py:66](C:/Users/Marek/Codex/Katalog/src/music_catalog_manager/services/scanner.py:66), [scanner.py:83](C:/Users/Marek/Codex/Katalog/src/music_catalog_manager/services/scanner.py:83); usuwanie: `services/library_cleanup.py`, gałąź `root_id`.
- Problem: ponowny skan nadrzędnego folderu przypisuje jego `root_id` również utworom wcześniej przypisanym osobno zarejestrowanemu podfolderowi.
- Dowód: podfolder miał jeden utwór; po ponownym skanie rodzica miał zero. Po usunięciu rodzica z katalogu nie pozostał żaden utwór, chociaż podfolder nadal był zarejestrowany.
- Wpływ: liczniki i zakresy folderów zależą od kolejności skanów. Usunięcie rodzica może usunąć z katalogu również utwory innego zarejestrowanego folderu i ich wpisy w playlistach. Pliki audio pozostają na dysku.
- Minimalna poprawka: ustalić deterministyczną regułę własności, np. najgłębszy zarejestrowany folder, i stosować ją przy dodawaniu, skanowaniu i usuwaniu. Alternatywnie blokować nakładające się rejestracje z czytelnym wyjaśnieniem. Nie wystarczy poprawić samą funkcję usuwania.

### B3. Metadane albumu mogą połączyć różnych wykonawców

- **Ważność: Średni. Potwierdzony.**
- Lokalizacja: [library_views.py:572](C:/Users/Marek/Codex/Katalog/src/music_catalog_manager/ui/library_views.py:572), [library_views.py:595](C:/Users/Marek/Codex/Katalog/src/music_catalog_manager/ui/library_views.py:595).
- Problem: wybór „Album metadata” uznaje zaznaczenie za jeden album wyłącznie na podstawie jego nazwy. Następnie wyszukuje wydanie pierwszego wykonawcy i dopasowuje utwory numerem płyty/utworu.
- Dowód: zaznaczono dwa „Greatest Hits”, wykonawców A i B, oba z numerem utworu 1. Przy zasymulowanej odpowiedzi MusicBrainz i zaakceptowanym podglądzie obie pozycje otrzymały wykonawcę A. Nie wykonywano żądań sieciowych ani zapisu do prawdziwej muzyki.
- Wpływ: program proponuje niewłaściwe zmiany, a zbiorcze zatwierdzenie zapisuje błędne tagi w katalogu; późniejszy zapis może przenieść je do audio. Podgląd pozwala zauważyć problem, dlatego nie oceniono go jako wysokiej ważności.
- Minimalna poprawka: weryfikować parę `(albumartist lub artist, album)` z taką samą normalizacją jak przeglądarka albumów; mieszanego zaznaczenia nie dopuszczać do automatycznego dopasowania.

### B4. Niezapisany identyfikator MusicBrainz znika z listy zmian oczekujących

- **Ważność: Średni. Potwierdzony.**
- Lokalizacja: [window.py:544](C:/Users/Marek/Codex/Katalog/src/music_catalog_manager/ui/window.py:544).
- Problem: po częściowym zapisie do pliku `dirty` porównuje jedynie dziesięć pól `FIELDS`, pomijając MBID nagrania, MBID albumu i ISRC, chociaż aplikacja obsługuje ich edycję.
- Dowód: zapisano MBID tylko w katalogu, a następnie zmieniono do pliku sam tytuł. MBID pozostał w bazie, plik miał pusty identyfikator, lecz `dirty` wyniosło 0. Nie zgłoszono błędu.
- Wpływ: filtr zmian oczekujących nie pokazuje utworu z niezapisanymi danymi; użytkownik może uznać synchronizację za zakończoną.
- Minimalna poprawka: jedna wspólna lista wszystkich zapisywalnych pól, używana przez zapis, weryfikację i porównanie stanu. Nie zerować `dirty`, dopóki którekolwiek z nich różni się od pliku.

### B5. Nadpisanie `folder.jpg` nie jest bezpieczne przy błędzie

- **Ważność: Średni. Potwierdzony na poziomie usługi.**
- Lokalizacja: [artwork.py:37](C:/Users/Marek/Codex/Katalog/src/music_catalog_manager/services/artwork.py:37).
- Problem: otwarcie pliku w `wb` następuje przed walidacją i zapisem nowego obrazu. Istniejący obraz jest natychmiast zerowany. Brakuje pliku tymczasowego i atomowej podmiany.
- Dowód: przekazanie nieprawidłowego obrazu do usługi zmniejszyło istniejący JPEG z 633 do 0 bajtów, a następnie zgłosiło `UnidentifiedImageError`. Interfejs wcześniej waliduje obraz, co ogranicza ten konkretny scenariusz wejścia; nadal nie chroni istniejącej okładki przed błędem podczas ponownego kodowania lub zapisu.
- Wpływ: utrata poprzedniej okładki folderu przy nieudanej operacji.
- Minimalna poprawka: najpierw zwalidować obraz, zapisać do pliku tymczasowego w tym samym folderze i dopiero po udanym zakończeniu podmienić cel; respektować decyzję dotyczącą nadpisania także przy końcowej podmianie.

### B6. Albumy wielopłytowe odtwarzają utwory w złej kolejności

- **Ważność: Średni. Potwierdzony.**
- Lokalizacja: [library_views.py:346](C:/Users/Marek/Codex/Katalog/src/music_catalog_manager/ui/library_views.py:346), [library.py:65](C:/Users/Marek/Codex/Katalog/src/music_catalog_manager/services/library.py:65).
- Problem: otwarcie albumu sortuje po numerze utworu; numer płyty nie jest wcześniejszym kluczem sortowania. Remis rozstrzyga techniczny identyfikator rekordu.
- Dowód: dla dwóch płyt uzyskano kolejność `2.1, 1.1, 2.2, 1.2` zamiast `1.1, 1.2, 2.1, 2.2`.
- Wpływ: ciągła kolejka działa, ale nie zachowuje kolejności albumu wielopłytowego.
- Minimalna poprawka: osobne sortowanie albumowe: numeryczna płyta, numeryczny utwór, stabilny klucz pomocniczy. Ręczne sortowanie tabeli może nadal działać niezależnie.

## 3. Bezpieczeństwo

### S1. Eksport CSV pozostawia aktywne formuły w tagach

- **Ważność: Średni. Potwierdzony eksport; nie wykonywano formuł w Excelu.**
- Lokalizacja: [export.py:30](C:/Users/Marek/Codex/Katalog/src/music_catalog_manager/services/export.py:30).
- Tagi są nieufnymi danymi z plików i zewnętrznych metadanych. `csv.DictWriter` zabezpiecza separatory, lecz nie semantykę formuł arkusza. Tytuł `=1+1` pozostał identyczny w wyeksportowanej komórce.
- Wpływ: program arkuszowy może potraktować tag jako formułę. Skutki zależą od formuły, aplikacji i jej zabezpieczeń; nie potwierdzano wykonania poleceń ani wycieku danych.
- Minimalna poprawka: zaoferować eksport przeznaczony do arkuszy, z tekstowym typem komórek w XLSX lub neutralizacją prefiksów formuł w CSV i testami w docelowych programach. Dla CSV strategia musi uwzględniać cudzysłowy i odbiorcę; zwykłe cytowanie CSV nie wystarcza. Zachować oddzielny eksport surowych danych do wymiany maszynowej.
- Źródło: [OWASP CSV Injection](https://community.owasp.org/attacks/CSV_Injection).

### Elementy zabezpieczone poprawnie

- Zapytania biblioteki stosują parametry oraz zamkniętą listę pól filtrów i sortowania. Są testy prób SQL injection.
- Import XML odrzuca DTD/ENTITY, również przy kodowaniach UTF-16; playlisty mają limit 8 MiB.
- ZIP ogranicza ścieżki, liczbę wpisów i rozmiary, sprawdza manifest i skróty; problem B1 dotyczy dalszej walidacji bazy, a nie klasycznego ZIP Slip.
- Zapis tagów odbywa się przez kopię roboczą i podmianę, z kontrolą zmiany oryginału podczas operacji. Obrazy mają ograniczenie bajtów i pikseli.
- Aplikacja desktopowa nie zawiera własnego serwera WWW, logowania ani sesji użytkowników. CORS i CSRF nie są tu bezpośrednimi mechanizmami wymagającymi wdrożenia. `runFullTrust` jest świadomie zadeklarowaną właściwością klasycznej aplikacji, a nie samodzielną podatnością.
- Ukierunkowany przegląd tekstów `src`, `scripts`, `packaging`, `docs` nie ujawnił dopasowań do badanych wzorców kluczy prywatnych i popularnych tokenów. Nie czytano magazynów poświadczeń ani plików uwierzytelniania. Nie jest to gwarancja braku sekretów w całym środowisku.

### Hipoteza wymagająca dalszej weryfikacji

`playlists.py:117–133` dopuszcza `file://host/...`, przekształca je w UNC i wywołuje `normalized()`, które rozwiązuje ścieżkę przez system plików. Należy sprawdzić, czy import nieufnej listy może niezamierzenie inicjować połączenia z obcym udziałem sieciowym. Nie wykonywano prób sieciowych ani testów uwierzytelniania SMB. Nie uznano wycieku poświadczeń za potwierdzony. Rozwiązaniem może być osobna zgoda na obce lokalizacje sieciowe i normalizacja tekstowa podczas samego dopasowywania wpisów.

## 4. Wydajność i jakość

### P1. Otwieranie playlisty wykonuje N+1 połączeń SQLite w wątku UI

- **Ważność: Średni. Potwierdzony pomiarem i ścieżką wywołania.**
- Lokalizacja: [playlists.py:45](C:/Users/Marek/Codex/Katalog/src/music_catalog_manager/services/playlists.py:45), [library_views.py:430](C:/Users/Marek/Codex/Katalog/src/music_catalog_manager/ui/library_views.py:430).
- Dla 500 wpisów otwarto **501 połączeń**, czas **0,448 s** na tym komputerze i sztucznej bazie. Nie należy liniowo ekstrapolować tego pomiaru na każde środowisko.
- `Play`, edycja i eksport playlist wywołują ten kod synchronicznie. Dodatkowo `window.py:279` materializuje wszystkie wyniki filtra na potrzeby kolejki, mimo stronicowania tabeli.
- Poprawka: jedno zapytanie z `JOIN playlist_tracks → tracks → artwork ORDER BY position`, zachowujące powtórzenia; budowanie większej kolejki w workerze. Docelowo kolejka identyfikatorów i doładowywanie danych porcjami.

### P2. Kopie przechowują wszystkie pliki cache w RAM, a ich lista dekompresuje ZIP w UI

- **Ważność: Średni. Potwierdzona konstrukcja kodu; nie wykonywano testu wyczerpania pamięci.**
- Lokalizacja: [backup.py:65](C:/Users/Marek/Codex/Katalog/src/music_catalog_manager/services/backup.py:65), [library_views.py:383](C:/Users/Marek/Codex/Katalog/src/music_catalog_manager/ui/library_views.py:383).
- `backup.create()` wczytuje bazę i cały cache obrazów do słownika bajtów. Obejmuje również nieużywane obrazy. `backups_dialog()` wywołuje pełną kontrolę i dekompresję każdego archiwum w głównym wątku.
- Wpływ: wzrost RAM proporcjonalny do całego cache; przy wielu dużych ZIP okno może przestać reagować. Obowiązkowa kopia przed czyszczeniem również podlega temu ograniczeniu.
- Poprawka: strumieniowe liczenie skrótów i pakowanie, zbieranie obrazów używanych przez snapshot, osobny odczyt lekkiego manifestu dla listy; pełna walidacja w workerze dopiero przed przywróceniem. Dodać retencję i kontrolowane porządkowanie cache.

### P3. Skan jednego folderu sprawdza dostępność całej biblioteki

- **Ważność: Średni. Potwierdzona konstrukcja kodu.**
- Lokalizacja: końcówka `services/scanner.py`, wywołanie `store.mark_availability()`; [store.py:150](C:/Users/Marek/Codex/Katalog/src/music_catalog_manager/database/store.py:150).
- Po każdym skanie wykonywany jest `is_file()` dla wszystkich utworów, również z innych dysków. Przy skanowaniu wielu rootów praca jest powtarzana. Ta pętla nie przyjmuje sygnału anulowania.
- Wpływ: niepotrzebne operacje dyskowe/sieciowe i opóźnione anulowanie; szczególnie odczuwalne przy niedostępnych udziałach i dużych katalogach.
- Poprawka: ograniczyć sprawdzanie do skanowanego rootu albo wykonać jeden przebieg po całym zadaniu, przekazywać anulowanie i raportować postęp. Nie zakładać usunięcia plików tylko z powodu błędu odczytu folderu.

### Q1. Pakowanie MSIX nie sprawdza, czy EXE odpowiada wersji manifestu

- **Ważność: Średni. Potwierdzona luka w procesie, nie błąd obecnie wydanego pakietu.**
- Lokalizacja: [build_msix.ps1:30](C:/Users/Marek/Codex/Katalog/scripts/build_msix.ps1:30).
- Skrypt sprawdza obecność EXE i kopiuje bieżący `dist`; nie buduje programu ani nie porównuje jego wersji z manifestem. Można więc utworzyć nową wersję MSIX ze starymi binariami. W tym audycie nie wykryto takiej rozbieżności w 1.5.1.0.
- Poprawka: jeden proces wydania, metadane kompilacji z wersją i hashami oraz obowiązkowe sprawdzenie wersji uruchomionego EXE przed pakowaniem.

### Q2. Wydania i kontrola jakości nie są domknięte w repozytorium

- **Ważność: Niski. Potwierdzone.**
- Lokalizacje: `pyproject.toml:16`, `scripts/package_sources.py:5`, `README.md:7`, bieżący `git status`.
- Wersje i nazwy artefaktów są powielone w skryptach, dokumentach i manifeście. Brakuje skonfigurowanego lintowania/type checkera i lokalnego katalogu workflow CI. Wiele zmian produktu pozostaje bez commita, więc ostatni commit nie identyfikuje pełnego źródła bieżącego wydania.
- Poprawka: jedno źródło wersji, kontrolowane renderowanie manifestów/nazw, etap CI dla testów i składni, stopniowe włączenie Ruff i typowania kluczowych usług. Po przeglądzie zapisać kod w Git i oznaczać wydania tagiem. Nie mieszać raportów dawnych wydań z wynikami nowych testów.

## 5. Brakujące testy

Obecne testy przechodzą, ponieważ nie pokrywają poniższych kombinacji:

1. Poprawny ZIP i SHA-256, ale brak wymaganej kolumny, nieobsługiwany trigger, błędny JSON tagów albo błąd migracji — aktywna baza musi pozostać niezmieniona.
2. Osobno dodany folder rodzic i dziecko, oba porządki skanowania, reimport list z rodzica i późniejsze usunięcie jednej rejestracji.
3. Dwa albumy o tej samej nazwie różnych wykonawców oraz składanka mająca wspólnego `albumartist`.
4. Częściowy zapis audio, gdy niezapisane pozostają MBID/ISRC; weryfikacja wszystkich pól i prawidłowego `dirty`.
5. Istniejący `folder.jpg`, nieprawidłowe wejście, błąd kodowania i błąd zapisu/pełny dysk — stare bajty muszą przetrwać.
6. Album wielopłytowy, brak numeru płyty, numery `01/12`, remisy i kolejność albumowej kolejki.
7. CSV z tagami zaczynającymi się od znaków formuł i znaków sterujących; osobne sprawdzenie pliku w Excelu/Calc oraz eksportu do wymiany danych.
8. Playlisty 10–100 tys. wpisów: liczba zapytań, RAM, czas reakcji UI i anulowanie. Dotychczasowe pomiary stronicowania nie zastępują tego scenariusza.
9. Wiele kopii ZIP i duży cache, odłączony dysk/NAS, zamknięcie okna przy długiej kontroli dostępności.
10. Niezgodna wersja EXE/manifestu MSIX, aktualizacja pakietu na izolowanym profilu i Windows App Certification Kit na wydaniu końcowym. Sam audyt nie uruchamiał instalatora ani nie zastępował używanej instalacji.

## 6. Propozycje funkcji

| Funkcja | Problem użytkownika i działanie | Priorytet | Zakres zmian |
|---|---|---|---|
| 1. Pomijanie niedostępnych lub uszkodzonych utworów | Jedna zła pozycja nie przerywa wieczoru z muzyką. Opcjonalne pominięcie, lista powodów i możliwość ponowienia. | MVP | Frontend: ustawienie i komunikaty; backend: automat kolejki; baza: bez migracji; testy: brak pliku, błąd dekodera, koniec listy. |
| 2. Odtwórz cały album/folder, Dodaj do kolejki, Odtwórz następny | Użytkownik nie musi rozumieć zależności między filtrem i zaznaczeniem ani przerywać aktualnej muzyki. Jawne polecenia w menu i przeglądarkach. | MVP | Frontend: akcje; backend: operacje kolejki i porządek płyt; baza: bez migracji; testy: kolejność, powtórzenia, aktywne odtwarzanie. |
| 3. Przywracanie sesji | Po restarcie wraca kolejka, bieżący utwór, pozycja i widok. Automatyczny start odtwarzania powinien być opcjonalny. | MVP | Frontend: ustawienie wznowienia; backend: zapis/odczyt sesji; baza: istniejące settings lub osobny model sesji; testy: brakujące pliki i nieaktualne identyfikatory. |
| 4. Przyrostowe monitorowanie folderów | Dodana muzyka pojawia się bez ręcznego pełnego skanowania. Obserwator scala zdarzenia i oferuje skan kontrolny. | Ważne | Frontend: stan monitorowania; backend: watcher i skaner przyrostowy; baza: istniejąca tożsamość pliku, ewentualny stan skanów; testy: przenoszenie, utrata dostępu, zagnieżdżenia. |
| 5. Inteligentne playlisty | Lista sama zbiera np. jazz FLAC lub utwory bez okładek. Reguły zapisane oddzielnie od ręcznej listy. | Ważne | Frontend: edytor reguł; backend: bezpieczne zapytania; baza: definicje reguł; testy: aktualizacja wyników, walidacja, brak SQL injection. |
| 6. Podgląd zmian przy reimporcie playlisty | Przed aktualizacją widać dodane, usunięte i nierozpoznane wpisy. Można zachować wcześniejsze pozycje i przywrócić poprzednią wersję listy. | Ważne | Frontend: porównanie przed/po; backend: plan importu i zastosowanie atomowe; baza: historia wersji lub snapshoty; testy: częściowe dopasowanie i anulowanie. |
| 7. Przenośna kopia kolekcji i retencja kopii | Kopia katalogu bez audio nie wystarcza do migracji na inny komputer. Opcjonalny pakiet z muzyką, względne lokalizacje i limity przechowywania. | Ważne | Frontend: kreator i zakres; backend: strumieniowe pakowanie, kontrola miejsca i odtwarzanie; baza: mapowanie lokalizacji/manifest; testy: duże pliki, przerwanie i kolizje. |
| 8. Normalizacja głośności ReplayGain | Różne albumy nie wymagają ciągłego przestawiania głośności. Odczyt istniejących tagów i opcjonalne wyrównanie bez modyfikacji audio. | Później | Frontend: tryb album/utwór i przełącznik; backend: odczyt tagów, przeliczenie poziomu i kontrola przesterowania; baza: opcjonalny cache wartości; testy: brak tagów i różne formaty. |

Nowe funkcje są propozycjami projektowymi, nie deklaracją istniejących możliwości. Zmiany schematu należy zaprojektować osobno i zatwierdzić przed migracją.

## 7. Plan działania

1. **Ochrona danych:** B1 i B2, następnie B5. Najpierw dodać reprodukcje do testów regresyjnych; dopiero potem poprawić walidację, własność folderów i atomowy zapis okładki.
2. **Poprawność metadanych i odtwarzania albumu:** B3, B4 i B6. Wspólne pojęcie tożsamości albumu i zestawu zapisywalnych pól. Dodać bezpieczny wariant eksportu S1.
3. **Responsywność:** usunąć N+1, przenieść budowanie kolejek i kontrolę ZIP do workerów, strumieniować kopie, ograniczyć i anulować kontrolę dostępności.
4. **Proces wydawania:** spójna wersja EXE/MSIX, testy regresji w CI, powtarzalne źródła i tag wydania; lintowanie wprowadzać stopniowo, bez masowego formatowania podczas napraw.
5. **Rozwój produktu:** najpierw funkcje 1–3, następnie monitorowanie folderów, inteligentne listy, podgląd importu i kopie przenośne. ReplayGain po ustabilizowaniu podstawowej kolejki i kontroli dużych bibliotek.

W audycie nie wdrożono powyższych napraw. Zakres pierwszej iteracji powinien obejmować ochronę danych i testy regresyjne, nie jednoczesne dodawanie wszystkich nowych funkcji.
