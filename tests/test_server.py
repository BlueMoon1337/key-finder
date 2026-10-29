import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from synth import progression

from keyfinder import audio
from keyfinder.server import create_app


@pytest.fixture
def client(tmp_path):
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
    return client.post("/api/songs", files={"file": ("My Song.wav", io.BytesIO(data), "audio/wav")},
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
    assert "no%20vocals" in export.headers["content-disposition"]

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


def test_rejects_path_tricks(client, song_bytes):
    song_id = upload(client, song_bytes).json()["id"]
    assert client.get("/api/songs/..%2F..%2Fetc").status_code == 404
    assert client.get(f"/api/songs/{song_id}/stems/..%2Fsong.json").status_code == 404
    assert client.get(f"/api/songs/{song_id}/stems/drums").status_code == 404
    assert client.get(f"/api/songs/{song_id}/stems/vocals?semitones=40").status_code == 422
    assert client.get(f"/api/songs/{song_id}/export", params={"volumes": "piano:1"}).status_code == 400


def test_static_app_is_served(client):
    res = client.get("/")
    assert res.status_code == 200 and "KeyFinder" in res.text
    assert client.get("/app.js").status_code == 200
    caps = client.get("/api/capabilities").json()
    assert "dsp" in caps["backends"]
