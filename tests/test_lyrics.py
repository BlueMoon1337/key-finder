"""Lyrics: LRCLIB lookups (with LRCLIB's answers recorded here), Whisper's words into lines, and both together."""

import urllib.error

import numpy as np
import pytest

from keyfinder import lyrics

SYNCED = """[00:20.50] No es con ejército, no es con fuerza
[00:26.00] Sino con su Santo Espíritu
[00:31.40]
[00:40.10] Yo venceré, yo venceré
"""
RECORD = {"id": 77, "trackName": "Yo Venceré", "artistName": "Danilo Montero", "duration": 300.0,
          "instrumental": False, "plainLyrics": "No es con ejército", "syncedLyrics": SYNCED}


def heard(*words):
    """Whisper's words: (text, start) pairs, each half a second long."""
    return [{"text": t, "start": s, "end": s + 0.5} for t, s in words]


@pytest.mark.parametrize("title, artist, first", [
    ("YO TE BUSCO | STEPHANIE CALZADILLA | CENTRO VIDA", "", ("YO TE BUSCO", "STEPHANIE CALZADILLA")),
    ("Marco Barrientos - Los Carros Del Faraón (Letra)", "", ("Los Carros Del Faraón", "Marco Barrientos")),
    ("Renuévame by Marcos Witt con letra en HD", "", ("Renuévame", "Marcos Witt")),
    ("Me Viniste a Rescatar (Live)", "", ("Me Viniste a Rescatar", "")),
    ("Alma Mía (Salmo 42)", "Kairo Worship | Encuentro Live", ("Alma Mía (Salmo 42)", "Kairo Worship")),
    ("Bondadoso [Video Oficial]", "Marcos Brunet", ("Bondadoso", "Marcos Brunet")),
])
def test_titles_are_cleaned_for_the_lookup(title, artist, first):
    assert lyrics.search_terms(title, artist)[0] == first


def test_either_order_of_a_dash_is_tried():
    pairs = lyrics.search_terms("Alma Mía (Salmo 42) - Kairo Worship")
    assert ("Alma Mía (Salmo 42)", "Kairo Worship") in pairs and ("Kairo Worship", "Alma Mía (Salmo 42)") in pairs


def test_lrc_lines_and_breaks():
    assert lyrics.parse_lrc(SYNCED) == [
        (20.5, "No es con ejército, no es con fuerza"), (26.0, "Sino con su Santo Espíritu"), (31.4, ""),
        (40.1, "Yo venceré, yo venceré")]
    assert lyrics.parse_lrc("[01:02.5][01:30.00]Coro") == [(62.5, "Coro"), (90.0, "Coro")]


def test_lookup_picks_the_synced_record_of_the_right_length():
    other = {**RECORD, "id": 1, "duration": 420.0}  # a live version, two minutes longer
    plain = {**RECORD, "id": 2, "syncedLyrics": None}
    urls = []

    def fetch(url):
        urls.append(url)
        return [other, plain, RECORD]

    found, why = lyrics.lookup("Yo Venceré", "Danilo Montero", 302.0, fetch)
    assert why is None and found["id"] == 77 and found["synced"][0] == (20.5, "No es con ejército, no es con fuerza")
    assert "track_name=Yo+Ven" in urls[0] and "artist_name=Danilo+Montero" in urls[0]
    assert lyrics.lookup("Otra Canción", "", 300.0, fetch) == (None, "LRCLIB has no lyrics for this song")


def test_lookup_without_the_network_says_so():
    def offline(url):
        raise urllib.error.URLError("blocked")

    assert lyrics.lookup("Yo Venceré", "", 300.0, offline) == (None, "LRCLIB couldn’t be reached")


def test_words_become_sung_lines():
    held = [{"text": "No", "start": 23.3, "end": 26.0}]  # a long note
    words = held + heard(("es", 26.9), ("con", 27.4), ("ejército,", 27.9), ("no", 30.6), ("es", 31.2),
                         ("con", 31.7), ("fuerza,", 32.2), ("sino", 39.3), ("con", 39.9), ("su", 40.4), ("santo", 40.9),
                  ("espíritu.", 41.4), ("Yo", 45.0))
    lines = [" ".join(w["text"] for w in ln["words"]) for ln in lyrics.split_lines(words)]
    # A held "No…" stays with its phrase; commas and pauses end lines, without their punctuation.
    assert lines == ["No es con ejército", "no es con fuerza", "sino con su santo espíritu", "Yo"]


def test_lrclib_words_are_timed_by_what_whisper_heard():
    lines = [(20.5, "No es con ejército"), (26.0, "Sino con su Santo Espíritu"), (40.1, "Yo venceré")]
    # This recording runs 3 s later than LRCLIB's; Whisper missed "Santo" and the whole last line.
    got = heard(("No", 23.5), ("es", 24.0), ("con", 24.5), ("ejercito", 25.0),
                ("sino", 29.0), ("con", 29.5), ("su", 30.0), ("espiritu", 31.4))
    timed, fit = lyrics.align(lines, got, 60.0)
    assert fit == pytest.approx(8 / 11)
    assert [w["text"] for w in timed[1]["words"]] == ["Sino", "con", "su", "Santo", "Espíritu"]  # LRCLIB's spelling
    assert timed[1]["words"][0]["start"] == 29.0
    santo = timed[1]["words"][3]
    assert 30.0 < santo["start"] <= santo["end"] <= 31.4  # between the heard words around it
    assert timed[2]["start"] == pytest.approx(43.1, abs=0.01)  # LRCLIB's time, moved by the 3 s


def test_find_prefers_lrclib_text_timed_by_whisper(monkeypatch):
    monkeypatch.setattr(lyrics, "available", lambda: True)
    monkeypatch.setattr(lyrics, "transcribe", lambda *a, **k: {"language": "es", "words": heard(
        ("No", 20.6), ("es", 21.0), ("con", 21.4), ("ejército,", 21.8), ("no", 23.0), ("es", 23.4), ("con", 23.8),
        ("fuerza", 24.2), ("sino", 26.1), ("con", 26.5), ("su", 26.9), ("santo", 27.3), ("espíritu", 27.7))})
    out = lyrics.find("Yo Venceré", "", 300.0, lambda: np.zeros(16000), fetch=lambda url: [RECORD])
    assert out["source"] == "lrclib" and out["lrclib"]["id"] == 77 and out["language"] == "es"
    assert [w["text"] for w in out["lines"][1]["words"]] == ["Sino", "con", "su", "Santo", "Espíritu"]
    assert out["lines"][1]["words"][3]["start"] == 27.3


def test_find_uses_whisper_when_lrclib_is_another_version(monkeypatch):
    monkeypatch.setattr(lyrics, "available", lambda: True)
    monkeypatch.setattr(lyrics, "transcribe", lambda *a, **k: {"language": "es", "words": heard(
        ("Tu", 10.0), ("fidelidad", 10.5), ("es", 11.0), ("grande", 11.5))})
    out = lyrics.find("Yo Venceré", "", 300.0, lambda: np.zeros(16000), fetch=lambda url: [RECORD])
    assert out["source"] == "whisper" and out["note"] == "LRCLIB’s lyrics are of another version of this song"
    assert [w["text"] for w in out["lines"][0]["words"]] == ["Tu", "fidelidad", "es", "grande"]


def test_online_only_keeps_lrclib_line_times(monkeypatch):
    out = lyrics.find("Yo Venceré", "", 300.0, None, mode="online", fetch=lambda url: [RECORD])
    assert out["source"] == "lrclib" and [ln["start"] for ln in out["lines"]] == [20.5, 26.0, 40.1]
    words = out["lines"][0]["words"]
    assert words[0]["start"] == 20.5
    assert all(a["end"] <= b["start"] + 1e-6 for a, b in zip(words, words[1:], strict=False))
    nothing = lyrics.find("Nada", "", 300.0, None, mode="online", fetch=lambda url: [])
    assert nothing["lines"] == [] and nothing["note"] == "LRCLIB has no lyrics for this song"


def test_editing_keeps_the_timing():
    lyr = {"source": "whisper", "lines": [
        {"start": 0.0, "end": 2.0, "words": heard(("Pondadoso", 0.0), ("asombroso", 1.0))},
        {"start": 3.0, "end": 5.0, "words": heard(("potente", 3.0), ("es", 4.0))}]}
    out = lyrics.edit(lyr, ["Bondadoso asombroso", ""])
    assert out["source"] == "edited" and out["edited_from"] == "whisper" and len(out["lines"]) == 1
    assert out["lines"][0]["words"][0] == {"start": 0.0, "end": 0.5, "text": "Bondadoso"}
    longer = lyrics.edit(lyr, ["Bondadoso, asombroso, potente", "es nuestro Señor"])
    assert [w["text"] for w in longer["lines"][1]["words"]] == ["es", "nuestro", "Señor"]
    assert longer["lines"][1]["words"][-1]["end"] == 5.0


def test_the_api_finds_edits_and_finds_again(tmp_path, monkeypatch):
    """A song gets its lyrics after it's ready; they can be corrected, and looked up again."""
    from fastapi.testclient import TestClient

    from keyfinder import audio
    from keyfinder.server import create_app

    asked = []
    monkeypatch.setattr(lyrics, "available", lambda: True)

    def transcribe(y, *a, **k):
        asked.append(y.size)
        return {"language": "es", "words": heard(("Pondadoso,", 1.0), ("asombroso", 1.6), ("potente", 2.2))}

    def offline(url):
        raise urllib.error.URLError("blocked")

    monkeypatch.setattr(lyrics, "transcribe", transcribe)
    monkeypatch.setattr(lyrics, "_get_json", offline)
    path = tmp_path / "Bondadoso.wav"
    audio.save(path, 0.2 * np.sin(2 * np.pi * 220 * np.arange(22050 * 4) / 22050), 22050)
    with TestClient(create_app(tmp_path / "data", inline=True)) as client:
        song_id = client.post("/api/songs", files={"file": ("Bondadoso.wav", path.read_bytes(), "audio/wav")},
                              data={"mode": "none"}).json()["id"]
        song = client.get(f"/api/songs/{song_id}").json()
        assert song["lyrics_status"] == "ready" and asked == [16000 * 4]  # the whole song: there's no vocals stem
        assert song["lyrics"]["source"] == "whisper" and song["lyrics_note"] == "LRCLIB couldn’t be reached"
        assert [w["text"] for w in song["lyrics"]["lines"][0]["words"]] == ["Pondadoso,", "asombroso", "potente"]

        fixed = client.put(f"/api/songs/{song_id}/lyrics", json={"lines": ["Bondadoso, asombroso, potente"]}).json()
        assert fixed["source"] == "edited" and fixed["lines"][0]["words"][0]["text"] == "Bondadoso,"

        assert client.post(f"/api/songs/{song_id}/lyrics", json={"mode": "online"}).status_code == 202
        song = client.get(f"/api/songs/{song_id}").json()
        assert song["lyrics_status"] == "none" and song["lyrics"] is None and len(asked) == 1  # online: no Whisper

        off = client.post("/api/songs", files={"file": ("Quiet.wav", path.read_bytes(), "audio/wav")},
                          data={"mode": "none", "lyrics": "off"}).json()
        assert client.get(f"/api/songs/{off['id']}").json()["lyrics_status"] == "off"
        caps = client.get("/api/capabilities").json()["lyrics"]
        assert caps["installed"] is True and caps["model"] == lyrics.MODEL
