"""Generate silent demo files only inside the selected new output directory."""
import argparse
import wave
from pathlib import Path
from music_catalog_manager.database.store import Store
from music_catalog_manager.services import metadata
from music_catalog_manager.services.scanner import scan

parser = argparse.ArgumentParser()
parser.add_argument('destination', type=Path)
args = parser.parse_args()
args.destination.mkdir(parents=True, exist_ok=False)
music = args.destination / 'Muzyka demonstracyjna'
music.mkdir()
for index, (artist, album, title, genre) in enumerate([
    ('Anna Nowak', 'Światło miasta', 'Poranek nad Wisłą', 'Jazz'),
    ('Anna Nowak', 'Światło miasta', 'Ostatni tramwaj', 'Jazz'),
    ('Północ', 'Daleko stąd', 'Łódź o świcie', 'Ambient'),
    ('Północ', 'Daleko stąd', 'Cisza', 'Ambient'),
    ('Jan Kowalski', 'Domowe nagrania', 'Pierwszy szkic', 'Acoustic'),
]):
    path = music / (str(index+1) + '.wav')
    with wave.open(str(path), 'wb') as file:
        file.setparams((1, 2, 44100, 0, 'NONE', 'not compressed'))
        file.writeframes(b'\0\0' * 4410)
    metadata.write_safe(path, dict(artist=artist, album=album, title=title, genre=genre, date='2026', tracknumber=str(index+1)))
store = Store(args.destination / 'profile')
store.set_setting('language', 'pl')
store.set_setting('theme', 'dark')
scan(store, store.add_root(music), hashes=True)
