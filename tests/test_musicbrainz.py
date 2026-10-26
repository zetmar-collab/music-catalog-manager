import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import httpx
import pytest
from music_catalog_manager.services.musicbrainz import MusicBrainz, Cancelled

MBID = '12345678-1234-1234-1234-123456789012'


def test_matches_cache_and_cover(tmp_path):
    calls = []
    def handler(request):
        calls.append(request)
        if 'coverartarchive' in request.url.host:
            return httpx.Response(404)
        return httpx.Response(200, json={'recordings': [{'id': MBID, 'title': 'Żółć', 'score': 90,
            'artist-credit': [{'name': 'Test'}], 'releases': [{'id': MBID, 'title': 'Album', 'date': '2026'}]}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = MusicBrainz(tmp_path, 'test@example.org', client=http)
        tags = {'title': 'Żółć', 'artist': 'Test', 'album': 'Album'}
        before = tags.copy()
        rows = client.search(tags)
        assert rows[0]['musicbrainz_albumid'] == MBID
        assert rows[0]['score'] == 90
        assert client.search(tags) == rows and len(calls) == 1
        assert tags == before
        assert client.cover(MBID) is None


def test_global_rate_limit(tmp_path):
    starts = []
    def handler(request):
        starts.append(time.monotonic())
        return httpx.Response(200, json={'recordings': []})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        clients = [MusicBrainz(tmp_path, 'test@example.org', client=http) for _ in range(2)]
        with ThreadPoolExecutor(2) as executor:
            list(executor.map(lambda pair: pair[1].search({'title': str(pair[0])}), enumerate(clients)))
    assert starts[1] - starts[0] >= 1.0


def test_retries_timeout_cancel_and_contact(tmp_path):
    count = 0
    def handler(request):
        nonlocal count
        count += 1
        return httpx.Response(503 if count < 3 else 200, json={'recordings': []})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = MusicBrainz(tmp_path, 'test@example.org', client=http)
        with patch.object(client, 'wait'):
            assert client.search({'title': 'Retry'}) == []
        assert count == 3
        client.cancel.set()
        with pytest.raises(Cancelled):
            client.search({'title': 'Cancel'})
    with pytest.raises(ValueError):
        MusicBrainz(tmp_path, '')
    def timeout(request):
        raise httpx.ReadTimeout('offline')
    with httpx.Client(transport=httpx.MockTransport(timeout)) as http:
        client = MusicBrainz(tmp_path, 'test@example.org', client=http)
        with patch.object(client, 'wait'), pytest.raises(httpx.ReadTimeout):
            client.search({'title': 'Offline'})


def test_release_mbid_lookup_and_image_response(tmp_path):
    import io
    from PIL import Image
    image = io.BytesIO()
    Image.new('RGB', (16, 16)).save(image, 'JPEG')
    def handler(request):
        if request.url.host == 'coverartarchive.org':
            return httpx.Response(200, content=image.getvalue())
        return httpx.Response(200, json={'id': MBID, 'title': 'Album', 'artist-credit': [{'name': 'Artist'}],
            'media': [{'tracks': [{'recording': {'id': MBID, 'title': 'Song'}}]}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = MusicBrainz(tmp_path, 'test@example.org', client=http)
        assert client.search({'musicbrainz_albumid': MBID})[0]['album'] == 'Album'
        assert client.cover(MBID) == image.getvalue()
