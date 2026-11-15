"""Transposing audio files: add a file, see its key, save it in another key and speed."""

import io
import os
import time
from urllib.parse import quote

import numpy as np
import pytest
from fastapi.testclient import TestClient
from synth import SR, progression

from keyfinder import analysis, audio
from keyfinder.server import create_app
from keyfinder.transposer import KEEP_SECONDS, Transposer

D_MAJOR = [(2, "maj"), (9, "maj"), (11, "min"), (7, "maj")]  # D A Bm G


@pytest.fixture
def song(tmp_path):
    path = tmp_path / "Mi Canción.wav"
    audio.save(path, progression(D_MAJOR, bpm=100, repeats=3), SR)
    return path


def test_a_file_is_transposed_and_saved(tmp_path, song):
    with TestClient(create_app(tmp_path / "data", inline=True)) as client:
        info = client.post("/api/transpose", files={"file": (song.name, song.read_bytes(), "audio/wav")}).json()
        assert info["key"]["name"] == "D major" and info["name"] == "Mi Canción"
        assert info["bpm"] == pytest.approx(100, rel=0.03)
        assert client.get("/api/songs").json() == []  # not added to the library

        res = client.get(f"/api/transpose/{info['id']}/render", params={"semitones": 2, "format": "wav"})
        assert res.status_code == 200
        assert quote("Mi Canción (E major).wav") in res.headers["content-disposition"]
        out = tmp_path / "out.wav"
        out.write_bytes(res.content)
        y = audio.load(out, audio.ANALYSIS_SR)
        assert analysis.analyze_signal(y)["key"]["name"] == "E major"
        assert y.size / audio.ANALYSIS_SR == pytest.approx(info["duration"], abs=0.2)

        slow = client.get(f"/api/transpose/{info['id']}/render",
                          params={"semitones": -12, "speed": 0.5, "format": "mp3"})
        assert quote("(D major, 50%).mp3") in slow.headers["content-disposition"]
        slowed = tmp_path / "slow.mp3"
        slowed.write_bytes(slow.content)
        seconds = audio.load(slowed, audio.ANALYSIS_SR).size / audio.ANALYSIS_SR
        assert seconds == pytest.approx(2 * info["duration"], rel=0.03)

        assert client.get(f"/api/transpose/{info['id']}/render", params={"format": "ogg"}).status_code == 422
        assert client.get(f"/api/transpose/{info['id']}/render", params={"semitones": 13}).status_code == 422
        assert client.delete(f"/api/transpose/{info['id']}").status_code == 204
        assert client.get(f"/api/transpose/{info['id']}/render").status_code == 404
        assert client.get("/api/transpose/..%2Fsongs/render").status_code == 404


def test_unreadable_files_are_refused(tmp_path):
    with TestClient(create_app(tmp_path / "data", inline=True)) as client:
        res = client.post("/api/transpose", files={"file": ("notes.wav", io.BytesIO(b"not audio"), "audio/wav")})
        assert res.status_code == 400 and "couldn't read notes.wav" in res.json()["detail"]


def test_desktop_adds_files_by_path(tmp_path, song):
    with TestClient(create_app(tmp_path / "data", inline=True, token="t"), headers={"X-KeyFinder-Token": "t"}) as c:
        res = c.post("/api/transpose/local", json={"paths": [str(song), str(tmp_path / "missing.mp3")]}).json()
        assert [x["key"]["name"] for x in res["created"]] == ["D major"]
        assert res["failed"][0]["error"] == "not a file"
        assert song.exists()  # the original is copied, not moved


def test_files_are_forgotten_after_a_day(tmp_path, song):
    t = Transposer(tmp_path)
    old = t.add(song.name, _copy(song, tmp_path / "a.wav"))
    stale = time.time() - KEEP_SECONDS - 60
    os.utime(t.root / old["id"], (stale, stale))
    t.cleanup()
    assert not (t.root / old["id"]).exists()


def _copy(src, dest):
    dest.write_bytes(src.read_bytes())
    return dest


def test_a_short_file_is_refused(tmp_path):
    path = tmp_path / "blip.wav"
    audio.save(path, np.zeros(SR // 2), SR)
    with pytest.raises(audio.AudioError, match="shorter than 2 seconds"):
        Transposer(tmp_path).add(path.name, _copy(path, tmp_path / "b.wav"))
