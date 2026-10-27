import csv
import json
import os
import tempfile
from pathlib import Path

from music_catalog_manager.database.store import FIELDS
from music_catalog_manager.services.library import Library
from music_catalog_manager.services.musicbrainz import Cancelled


def export_library(store, options, destination, cancel, progress):
    destination = Path(destination)
    fd, name = tempfile.mkstemp(prefix='.mcm-export-', dir=destination.parent)
    os.close(fd)
    staged = Path(name)
    try:
        with staged.open('w', encoding='utf-8', newline='') as out:
            is_csv = destination.suffix.lower() == '.csv'
            if is_csv:
                writer = csv.DictWriter(out, fieldnames=['path', 'format', *FIELDS])
                writer.writeheader()
            else:
                out.write('[\n')
            count = 0
            for row in Library(store).all(cancel=cancel, **options):
                if cancel.is_set():
                    raise Cancelled()
                if is_csv:
                    writer.writerow({'path': row['path'], 'format': row['format'], **{k: row['tags'].get(k, '') for k in FIELDS}})
                else:
                    if count:
                        out.write(',\n')
                    json.dump(row, out, ensure_ascii=False)
                count += 1
                if count % 250 == 0:
                    progress({'exported': count})
            if not is_csv:
                out.write('\n]\n')
        if cancel.is_set():
            raise Cancelled()
        os.replace(staged, destination)
        return count
    finally:
        staged.unlink(missing_ok=True)
