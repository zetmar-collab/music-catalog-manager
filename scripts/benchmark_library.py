"""Reproducible synthetic catalog benchmark, without touching the user's profile."""
import json
import tempfile
import time
import tracemalloc
from pathlib import Path

from music_catalog_manager.database.store import Store
from music_catalog_manager.services.library import Library


def main():
    results = []
    with tempfile.TemporaryDirectory(prefix='mcm-benchmark-') as folder:
        for count in (10000, 50000, 100000):
            store = Store(Path(folder) / str(count))
            with store.connection() as db:
                db.executemany('INSERT INTO tracks(path,tags,format,duration) VALUES(?,?,?,?)',
                    ((f'C:/Music/{i}.mp3', json.dumps(dict(title=f'Utwór {i:06}', artist=f'Łódź {i%400}',
                        album=f'Album {i//12}', genre='Jazz', date='2026', tracknumber=str(i%12+1)), ensure_ascii=False), 'MP3', 200) for i in range(count)))
            library = Library(store)
            tracemalloc.start()
            start = time.perf_counter()
            rows, total = library.page()
            page_ms = (time.perf_counter() - start) * 1000
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            start = time.perf_counter()
            matches, matched = library.page(query='łódź 12')
            search_ms = (time.perf_counter() - start) * 1000
            start = time.perf_counter()
            facets = library.facets()
            facet_ms = (time.perf_counter() - start) * 1000
            results.append(dict(tracks=total, loaded_rows=len(rows), page_ms=round(page_ms, 1),
                search_ms=round(search_ms, 1), matching_rows=matched, facets_ms=round(facet_ms, 1),
                page_python_peak_kib=round(peak/1024, 1)))
    destination = Path('reports/library-benchmark.json')
    destination.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(destination.read_text(encoding='utf-8'))


if __name__ == '__main__':
    main()
