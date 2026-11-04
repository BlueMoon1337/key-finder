import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def lyrics_offline(monkeypatch):
    """Songs added in tests find no lyrics: no LRCLIB requests, and no Whisper (whose model is 1.6 GB).

    Tests of lyrics put their own stand-ins in place of these.
    """
    import urllib.error

    from keyfinder import lyrics

    def offline(url):
        raise urllib.error.URLError("tests don't use the network")

    monkeypatch.setattr(lyrics, "_get_json", offline)
    monkeypatch.setattr(lyrics, "available", lambda: False)
