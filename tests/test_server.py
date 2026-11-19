import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from synth import progression

from keyfinder import ENGINE_API, audio
from keyfinder.server import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("KEYFINDER_UI_DIR", str(tmp_path / "no-ui"))
    app = create_app(tmp_path, inline=True)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def song_bytes(tmp_path):
    y = progression([(9, "min"), (2, "min"), (4, "maj"), (9, "min")], bpm=100, repeats=2)
    path = tmp_path / "song.wav"
    audio.save(path, np.vstack([y, y]), 22050)
    return path.read_bytes()


def upload(client, data, mode="2stems"):
    return upload_named(client, data, "My Song.wav", mode)


def upload_named(client, data, name, mode="none"):
    return client.post("/api/songs", files={"file": (name, io.BytesIO(data), "application/octet-stream")},
                       data={"mode": mode, "backend": "dsp"})


def test_full_flow(client, song_bytes):
    res = upload(client, song_bytes)
    assert res.status_code == 201, res.text
    song_id = res.json()["id"]

    song = client.get(f"/api/songs/{song_id}").json()
    assert song["status"] == "ready", song["error"]
    assert song["title"] == "My Song"
    assert song["stems"] == ["original", "vocals", "accompaniment"]
    assert song["analysis"]["key"]["name"] == "A minor"
    assert song["analysis"]["bpm"] == pytest.approx(100, rel=0.02)
    assert "source" not in song

    listing = client.get("/api/songs").json()
    assert listing[0]["key"] == "A minor" and listing[0]["camelot"] == "8A"

    stem = client.get(f"/api/songs/{song_id}/stems/vocals")
    assert stem.status_code == 200 and stem.headers["content-type"] == "audio/mpeg"
    shifted = client.get(f"/api/songs/{song_id}/stems/vocals?semitones=-2")
    assert shifted.status_code == 200 and len(shifted.content) > 1000

    export = client.get(f"/api/songs/{song_id}/export",
                        params={"semitones": 1, "speed": 0.8, "volumes": "vocals:0,accompaniment:1", "format": "wav"})
    assert export.status_code == 200
    assert "no%20Vocals" in export.headers["content-disposition"]

    assert client.delete(f"/api/songs/{song_id}").status_code == 204
    assert client.get(f"/api/songs/{song_id}").status_code == 404


def test_analysis_only(client, song_bytes):
    song_id = upload(client, song_bytes, mode="none").json()["id"]
    song = client.get(f"/api/songs/{song_id}").json()
    assert song["stems"] == ["original"]


def test_rejects_bad_input(client, song_bytes):
    assert upload(client, song_bytes, mode="9stems").status_code == 400
    assert client.post("/api/songs", files={"file": ("x.wav", io.BytesIO(b""), "audio/wav")}).status_code == 400
    bad = upload(client, b"this is not audio")
    song = client.get(f"/api/songs/{bad.json()['id']}").json()
    assert song["status"] == "error" and song["error"]


def test_too_short_is_a_clear_error(client, tmp_path):
    path = tmp_path / "blip.wav"
    audio.save(path, np.zeros(2000), 22050)
    song_id = upload_named(client, path.read_bytes(), "blip.wav").json()["id"]
    song = client.get(f"/api/songs/{song_id}").json()
    assert song["status"] == "error" and "at least" in song["error"]


def test_rejects_path_tricks(client, song_bytes):
    song_id = upload(client, song_bytes).json()["id"]
    assert client.get("/api/songs/..%2F..%2Fetc").status_code == 404
    assert client.get(f"/api/songs/{song_id}/stems/..%2Fsong.json").status_code == 404
    assert client.get(f"/api/songs/{song_id}/stems/drums").status_code == 404
    assert client.get(f"/api/songs/{song_id}/stems/vocals?semitones=40").status_code == 422
    assert client.get(f"/api/songs/{song_id}/export", params={"volumes": "piano:1"}).status_code == 400


def test_built_ui_is_served(tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "index.html").write_text("<title>KeyFinder UI</title>")
    with TestClient(create_app(tmp_path / "data", inline=True, ui_dir=ui)) as c:
        assert "KeyFinder UI" in c.get("/").text
        caps = c.get("/api/capabilities").json()
        assert "dsp" in caps["backends"] and caps["desktop"] is False
        assert caps["api"] == ENGINE_API >= 1


def test_without_built_ui_explains_how_to_build(client, monkeypatch):
    res = client.get("/")
    assert res.status_code == 200 and "npm run build" in res.text


def test_metadata_cover_and_editing(client, tmp_path):
    t = np.arange(22050 * 4) / 22050
    path = tmp_path / "tagged.m4a"
    audio.save(path, np.vstack([np.sin(2 * np.pi * 220 * t)] * 2) * 0.3, 22050)
    song_id = upload_named(client, path.read_bytes(), "tagged.m4a").json()["id"]
    song = client.get(f"/api/songs/{song_id}").json()
    assert song["artist"] == "" and song["cover"] is False
    assert client.get(f"/api/songs/{song_id}/cover").status_code == 404

    edited = client.patch(f"/api/songs/{song_id}", json={"title": "Renamed", "artist": "Someone"}).json()
    assert (edited["title"], edited["artist"]) == ("Renamed", "Someone")
    assert client.patch(f"/api/songs/{song_id}", json={"title": "  "}).status_code == 400
    original = client.get(f"/api/songs/{song_id}/stems/original", params={"download": True})
    assert "Renamed.mp3" in original.headers["content-disposition"]


def test_url_import_refuses_local_addresses(client):
    for url in ["http://127.0.0.1:8000/song.mp3", "http://localhost/x.mp3", "file:///etc/passwd",
                "https://www.youtube.com/watch?v=abc"]:
        res = client.post("/api/songs/url", json={"url": url, "mode": "none"})
        assert res.status_code == 400, url


def test_desktop_token_and_local_import(tmp_path, song_bytes):
    token = "t" * 40
    source = tmp_path / "picked.wav"
    source.write_bytes(song_bytes)
    with TestClient(create_app(tmp_path / "data", inline=True, token=token)) as c:
        assert c.get("/api/songs").status_code == 403
        assert c.get("/api/songs", headers={"X-KeyFinder-Token": "wrong"}).status_code == 403
        auth = {"X-KeyFinder-Token": token}
        res = c.post("/api/songs/local", headers=auth,
                     json={"paths": [str(source), "relative.wav", str(tmp_path / "missing.wav")], "mode": "none"})
        body = res.json()
        assert res.status_code == 201 and len(body["created"]) == 1 and len(body["failed"]) == 2
        assert c.get("/api/songs", headers=auth).json()[0]["status"] == "ready"
        bad = c.post("/api/songs/local", headers=auth, json={"paths": [str(source)], "mode": "9stems"})
        assert bad.status_code == 400


def test_local_import_only_exists_in_desktop_mode(client, tmp_path):
    assert client.post("/api/songs/local", json={"paths": ["/etc/hosts"]}).status_code in (404, 405)


def test_tempo_can_be_doubled_and_halved(client, song_bytes):
    song_id = upload(client, song_bytes, mode="none").json()["id"]
    before = client.get(f"/api/songs/{song_id}").json()["analysis"]
    doubled_bpm = client.patch(f"/api/songs/{song_id}", json={"tempo": "double"}).json()["bpm"]
    assert doubled_bpm == pytest.approx(2 * before["bpm"], abs=0.2)
    doubled = client.get(f"/api/songs/{song_id}").json()["analysis"]
    assert len(doubled["beats"]) == 2 * len(before["beats"]) - 1
    assert set(before["beats"]) <= set(doubled["beats"])
    client.patch(f"/api/songs/{song_id}", json={"tempo": "half"})
    back = client.get(f"/api/songs/{song_id}").json()["analysis"]
    assert back["beats"] == before["beats"] and back["bpm"] == pytest.approx(before["bpm"], abs=0.2)
    assert client.patch(f"/api/songs/{song_id}", json={"tempo": "triple"}).status_code == 422


def test_a_song_that_changes_tempo(client, tmp_path):
    from synth import SR, progression

    chords = [(2, "maj"), (9, "maj"), (11, "min"), (7, "maj")]
    y = np.concatenate([progression(chords, bpm=90, repeats=6), progression(chords, bpm=120, repeats=6)])
    path = tmp_path / "medley.wav"
    audio.save(path, y, SR)
    song_id = upload_named(client, path.read_bytes(), "medley.wav").json()["id"]
    summary = next(s for s in client.get("/api/songs").json() if s["id"] == song_id)
    assert summary["bpm"] == pytest.approx(90, rel=0.02)
    assert summary["tempos"] == [pytest.approx(90, rel=0.02), pytest.approx(120, rel=0.02)]
    # ½× / 2× scale every section.
    client.patch(f"/api/songs/{song_id}", json={"tempo": "double"})
    sections = client.get(f"/api/songs/{song_id}").json()["analysis"]["tempo_sections"]
    assert [s["bpm"] for s in sections] == [pytest.approx(180, rel=0.02), pytest.approx(240, rel=0.02)]


def test_summaries_list_the_chords_a_song_uses(client, tmp_path):
    from synth import SR, progression

    path = tmp_path / "chords.wav"
    audio.save(path, progression([(2, "maj"), (9, "maj"), (11, "min"), (7, "maj")], bpm=100), SR)
    song_id = upload_named(client, path.read_bytes(), "chords.wav").json()["id"]
    summary = next(s for s in client.get("/api/songs").json() if s["id"] == song_id)
    assert {"2:maj", "9:maj", "11:min", "7:maj"} <= set(summary["chords"])  # D A Bm G
