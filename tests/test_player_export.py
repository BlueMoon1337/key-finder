import io
import re
import struct
import zipfile
from urllib.parse import quote

import numpy as np
import pytest

from keyfinder import player_export

# Player's parseSongName (src/import/multitracks.ts), which reads the key and tempo.
PLAYER_NAME = re.compile(r"^(.+?)-(.+)-([A-G](?:#|b)?m?)-(\d+(?:\.\d+)?)\s*bpm$", re.IGNORECASE)


def song(**overrides):
    analysis = {
        "key": {"tonic": 2, "mode": "minor", "name": "D minor"},
        "bpm": 120.0,
        "beats": [0.5 * i for i in range(16)],
        "downbeats": [0.0, 2.0, 4.0, 6.0],
        "key_sections": [],
    }
    analysis.update(overrides.pop("analysis", {}))
    return {"title": "Yo Venceré", "artist": "Danilo Montero", "stems": ["vocals", "accompaniment", "original"],
            "analysis": analysis, **overrides}


def read_wav(data: bytes) -> dict:
    """The chunks Player's readWav (src/audio/wav.ts) reads metadata from."""
    assert data[:4] == b"RIFF" and data[8:12] == b"WAVE"
    out = {"cues": {}, "labels": {}}
    off = 12
    while off + 8 <= len(data):
        cid, size = data[off:off + 4], struct.unpack("<I", data[off + 4:off + 8])[0]
        body = data[off + 8:off + 8 + size]
        if cid == b"fmt ":
            out["fmt"] = struct.unpack("<HHIIHH", body[:16])
        elif cid == b"data":
            out["frames"] = size // out["fmt"][4]
        elif cid == b"acid":
            out["den"], out["num"], out["bpm"] = struct.unpack("<HHf", body[16:24])
        elif cid == b"cue ":
            for i in range(struct.unpack("<I", body[:4])[0]):
                e = body[4 + 24 * i:28 + 24 * i]
                out["cues"][struct.unpack("<I", e[:4])[0]] = struct.unpack("<I", e[20:24])[0]
        elif cid == b"LIST":
            o = 4
            while o + 8 <= len(body):
                sid, ssize = body[o:o + 4], struct.unpack("<I", body[o + 4:o + 8])[0]
                sub = body[o + 8:o + 8 + ssize]
                if body[:4] == b"INFO":
                    out[sid.decode()] = sub.rstrip(b"\0").decode()
                elif sid == b"labl":
                    out["labels"][struct.unpack("<I", sub[:4])[0]] = sub[4:].rstrip(b"\0").decode()
                o += 8 + ssize + (ssize & 1)
        off += 8 + size + (size & 1)
    return out


def test_name_gives_player_the_key_and_tempo():
    name = player_export.package_name(song())
    assert name == "Yo Venceré-Danilo Montero-Dm-120.00bpm"
    m = PLAYER_NAME.match(name)
    assert m.groups() == ("Yo Venceré", "Danilo Montero", "Dm", "120.00")


def test_name_follows_pitch_and_speed_and_survives_hyphens():
    name = player_export.package_name(song(title="Para Danzar - Medley", artist=""), semitones=-2, speed=0.9)
    m = PLAYER_NAME.match(name)
    assert m.groups() == ("Para Danzar – Medley", "KeyFinder", "Cm", "108.00")
    assert player_export.player_key(7, "major", 1) == "Ab"
    assert player_export.player_key(6, "minor") == "F#m"


def test_click_accents_the_downbeats():
    sr = player_export.SR
    y = player_export.click_track([0.0, 0.5, 1.0, 1.5, 2.0], [0.0, 2.0], int(2.5 * sr))
    peaks = [np.abs(y[int(t * sr):int(t * sr) + 600]).max() for t in (0.0, 0.5, 1.0, 1.5, 2.0)]
    assert peaks[0] > peaks[1] * 1.3 and peaks[4] > peaks[3] * 1.3
    assert np.abs(y[int(0.2 * sr):int(0.45 * sr)]).max() == 0


@pytest.fixture
def song_folder(tmp_path):
    from keyfinder import audio

    sr = player_export.SR
    t = np.arange(sr * 8) / sr
    (tmp_path / "stems").mkdir()
    for stem, freq in (("vocals", 440), ("accompaniment", 220), ("original", 330)):
        audio.save(tmp_path / "stems" / f"{stem}.mp3", np.vstack([0.3 * np.sin(2 * np.pi * freq * t)] * 2), sr)
    return tmp_path


def test_package_is_laid_out_as_player_imports_it(song_folder):
    sections = [{"start": 0.0, "end": 4.0, "tonic": 2, "mode": "minor"},
                {"start": 4.0, "end": 8.0, "tonic": 0, "mode": "minor"}]
    s = song(analysis={"key_sections": sections})
    dest = player_export.build(s, song_folder, song_folder / "out.zip", semitones=2, speed=0.5)
    with zipfile.ZipFile(dest) as zf:
        names = zf.namelist()
        root = "Yo Venceré-Danilo Montero-Em-60.00bpm/MultiTracks/"
        stems = ("Vocals.wav", "Backing.wav", "Reference.wav", "Click Track.wav")
        assert sorted(names) == sorted(root + f for f in stems)
        assert all(i.compress_type == zipfile.ZIP_STORED for i in zf.infolist())
        wav = read_wav(zf.read(root + "Vocals.wav"))
        click = read_wav(zf.read(root + "Click Track.wav"))
    sr = player_export.SR
    assert wav["fmt"][:3] == (1, 2, sr) and click["fmt"][1] == 1
    assert wav["frames"] == pytest.approx(16 * sr, rel=0.01)  # 8 s at half speed
    assert click["frames"] == wav["frames"]
    assert (wav["num"], wav["den"], round(wav["bpm"], 2)) == (4, 4, 60.0)
    assert wav["INAM"] == "Yo Venceré" and wav["IART"] == "Danilo Montero"
    assert wav["ISFT"] == "KeyFinder"  # how Player knows the name's second slot is the artist
    # Key changes become sections, transposed and at the new speed.
    assert [(wav["cues"][i], wav["labels"][i]) for i in (1, 2)] == [(0, "E minor"), (8 * sr, "D minor")]


def test_unsplit_song_and_cover(song_folder):
    (song_folder / "cover.jpg").write_bytes(b"\xff\xd8\xff\xe0 not really a jpeg")
    dest = player_export.build(song(stems=["original"]), song_folder, song_folder / "out.zip")
    with zipfile.ZipFile(dest) as zf:
        names = {n.split("/", 1)[1] for n in zf.namelist()}
        assert names == {"MultiTracks/Song.wav", "MultiTracks/Click Track.wav", "Album.jpg"}
        assert not read_wav(zf.read(zf.namelist()[0]))["cues"]  # one key: no sections to mark


def test_server_exports_for_player(tmp_path):
    from fastapi.testclient import TestClient

    from keyfinder import audio
    from keyfinder.server import create_app

    t = np.arange(22050 * 6) / 22050
    path = tmp_path / "song.wav"
    audio.save(path, 0.3 * np.sin(2 * np.pi * 220 * t) * (np.sin(2 * np.pi * 2 * t) > 0), 22050)
    with TestClient(create_app(tmp_path / "data", inline=True)) as client:
        res = client.post("/api/songs", files={"file": ("Song-Name.wav", path.read_bytes(), "audio/wav")},
                          data={"mode": "2stems", "backend": "dsp"})
        song_id = res.json()["id"]
        name = client.get(f"/api/songs/{song_id}/export/player-name", params={"semitones": 1}).json()["name"]
        assert PLAYER_NAME.match(name.removesuffix(".zip"))
        res = client.get(f"/api/songs/{song_id}/export", params={"format": "player", "semitones": 1})
        assert res.status_code == 200 and res.headers["content-type"] == "application/zip"
        assert quote(name) in res.headers["content-disposition"]
        with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
            assert sum(n.endswith(".wav") for n in zf.namelist()) == 4
