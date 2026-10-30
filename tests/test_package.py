"""Songs that arrive as stems: MultiTracks zips, folders of stems, Player songs, KeyFinder's exports."""

import io
import json
import zipfile

import numpy as np
import pytest
from fastapi.testclient import TestClient
from synth import SR, click, progression

from keyfinder import audio, player_export, stems
from keyfinder.server import create_app

D_MAJOR = [(2, "maj"), (9, "maj"), (11, "min"), (7, "maj")]  # D A Bm G
BPM = 120.0


@pytest.mark.parametrize("name, kind", [
    ("Click Track", "click"), ("Click", "click"), ("Guide", "guide"), ("Guide (Dynamic)", "guide"),
    ("MD", "guide"), ("Reference", "reference"), ("Original Song (Reference)", "reference"),
    ("Drums", "drums"), ("Drums (Studio)", "drums"), ("Kick", "drums"), ("Perc", "percussion"),
    ("Tambourine 2", "percussion"), ("Loop 1", "loops"), ("Bass", "bass"), ("Synth Bass 2", "bass"),
    ("Piano", "piano"), ("Keys 11", "keys"), ("Synth Pad", "keys"), ("Rhodes", "keys"), ("EG 1", "eg"),
    ("Electric Guitar 3", "eg"), ("Guitar", "eg"), ("AG", "ag"), ("Acoustic Guitar", "ag"),
    ("Strings", "strings"), ("Brass", "horns"), ("BGVs", "vocals"), ("Lead Vocal", "vocals"),
    ("Vocals", "vocals"), ("Vocal FX", "fx"), ("Gayageum", "aux"), ("Other", "aux"), ("Backing", "aux"),
])
def test_kinds_follow_players_rules(name, kind):
    assert stems.kind_of(name) == kind
    assert stems.kind_of(name + ".wav") == kind


def test_names_keys_and_files():
    assert stems.parse_song_name("Goodness of God-Victory-Ab-63.00bpm.zip") == {
        "title": "Goodness of God", "album": "Victory", "key": "Ab", "bpm": 63.0}
    assert stems.parse_song_name("Just a folder") == {"title": "Just a folder"}
    assert stems.parse_key("Ab") == (8, "major") and stems.parse_key("F#m") == (6, "minor")
    assert stems.parse_key("C# minor") == (1, "minor") and stems.parse_key("H") is None
    assert stems.display_names(["Song - Drums.wav", "Song - EG 1.wav"]) == ["Drums", "EG 1"]
    picked = stems.pick_files(["X/MultiTracks/Bass.wav", "X/Preview.mp3", "X/Album.jpg", "__MACOSX/X/._Bass.wav",
                               "X/MultiTracks/.DS_Store"])
    assert picked == {"stems": ["X/MultiTracks/Bass.wav"], "artwork": "X/Album.jpg"}
    used = {"original"}
    assert [stems.stem_id(n, used) for n in ("EG 1", "EG 1", "Original", "Click Track")] == [
        "eg-1", "eg-1-2", "original-2", "click-track"]


def beat_grid(seconds: float, bpm: float = BPM):
    beats = list(np.arange(0, seconds - 0.1, 60 / bpm))
    return beats, beats[::4]


def make_stems() -> dict[str, np.ndarray]:
    keys = progression(D_MAJOR, bpm=BPM, drums=False)
    beats, downbeats = beat_grid(keys.size / SR)
    drums = np.zeros_like(keys)
    k = click(SR)
    for b in beats:
        s = int(b * SR)
        drums[s:s + k.size] += 0.7 * k[: drums.size - s]
    return {
        "Keys": 0.5 * keys,
        "Drums": drums,
        "Click Track": player_export.click_track(beats, downbeats, keys.size, SR),
        "Guide": 0.05 * np.sin(2 * np.pi * 300 * np.arange(keys.size) / SR).astype(np.float32),
    }


def write_stems(folder, signals, prefix=""):
    folder.mkdir(parents=True, exist_ok=True)
    for name, y in signals.items():
        audio.save(folder / f"{prefix}{name}.wav", y, SR)


def zip_folder(folder, dest):
    with zipfile.ZipFile(dest, "w") as zf:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(folder.parent).as_posix())
    return dest


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "data", inline=True)) as c:
        yield c


@pytest.fixture
def desktop(tmp_path):
    with TestClient(create_app(tmp_path / "desk", inline=True, token="t"), headers={"X-KeyFinder-Token": "t"}) as c:
        yield c


def check_click_grid(analysis):
    assert analysis["sources"]["beats"] == "click"
    beats = np.asarray(analysis["beats"])
    assert np.allclose(np.diff(beats), 0.5, atol=0.01)
    assert analysis["downbeats"][:3] == pytest.approx([0.0, 2.0, 4.0], abs=0.01)
    assert analysis["beats_per_bar"] == 4


def test_multitracks_zip(client, tmp_path):
    root = tmp_path / "pkg" / "Test Song-Test Album-D-120.00bpm"
    write_stems(root / "MultiTracks", make_stems())
    audio.save(root / "Preview.mp3", np.zeros(SR * 3), SR)  # not a stem: outside MultiTracks/
    data = zip_folder(root, tmp_path / "Test Song-Test Album-D-120.00bpm.zip").read_bytes()
    res = client.post("/api/songs", files={"file": ("Test Song-Test Album-D-120.00bpm.zip", data, "application/zip")})
    assert res.status_code == 201
    song = client.get(f"/api/songs/{res.json()['id']}").json()
    assert song["status"] == "ready", song["error"]
    assert song["title"] == "Test Song" and song["mode"] == "stems"
    assert song["stems"] == ["original", "click-track", "drums", "guide", "keys"]
    assert song["stem_kinds"] == {"click-track": "click", "drums": "drums", "guide": "guide", "keys": "keys"}
    assert song["stem_names"]["click-track"] == "Click Track"
    a = song["analysis"]
    assert a["key"]["name"] == "D major" and a["sources"]["key"] == "name"
    assert a["bpm"] == 120.0 and a["sources"]["bpm"] == "name"
    check_click_grid(a)
    assert [c["root"] for c in a["chords"]["basic"][:4]] == [2, 9, 11, 7]
    # The original is the stems mixed (no reference in the package), and plays and downloads.
    assert client.get(f"/api/songs/{song['id']}/stems/original").status_code == 200
    assert "Keys" in client.get(f"/api/songs/{song['id']}/stems/keys?download=true").headers["content-disposition"]


def test_folder_of_stems_finds_the_key_itself(desktop, tmp_path):
    folder = tmp_path / "My Stems"
    write_stems(folder, make_stems(), prefix="My Song - ")
    res = desktop.post("/api/songs/local", json={"paths": [str(folder)]}).json()
    assert not res["failed"]
    song = desktop.get(f"/api/songs/{res['created'][0]['id']}").json()
    assert song["status"] == "ready", song["error"]
    assert song["title"] == "My Stems"
    assert sorted(song["stem_names"].values()) == ["Click Track", "Drums", "Guide", "Keys"]  # prefix gone
    a = song["analysis"]
    assert a["key"]["name"] == "D major" and a["sources"]["key"] == "audio"
    check_click_grid(a)
    empty = tmp_path / "Empty"
    empty.mkdir()
    assert desktop.post("/api/songs/local", json={"paths": [str(empty)]}).json()["failed"][0]["error"]


def test_player_song_folder(desktop, tmp_path):
    folder = tmp_path / "Player Library" / "Songs" / "song_abc"
    signals = make_stems()
    files = {"Keys": "keys.wav", "Drums": "drums.wav", "Click Track": "click.wav"}
    folder.mkdir(parents=True)
    for name, file in files.items():
        audio.save(folder / file, signals[name], SR)
    (folder / "song.json").write_text(json.dumps({
        "version": 1, "id": "song_abc", "title": "From Player", "artist": "The Band", "key": "Bm", "bpm": 120,
        "timeSig": [4, 4], "clickOffset": 0, "duration": 16, "sections": [],
        "stems": [{"id": "s1", "name": "Keys", "file": "keys.wav"}, {"id": "s2", "name": "Drums", "file": "drums.wav"},
                  {"id": "s3", "name": "Metro", "file": "click.wav"}],
        "clickStem": "s3",
    }))
    song_id = desktop.post("/api/songs/local", json={"paths": [str(folder)]}).json()["created"][0]["id"]
    song = desktop.get(f"/api/songs/{song_id}").json()
    assert song["status"] == "ready", song["error"]
    assert (song["title"], song["artist"]) == ("From Player", "The Band")
    assert song["stem_kinds"]["metro"] == "click"  # Player's clickStem, whatever it's called
    assert song["analysis"]["key"]["name"] == "B minor"  # Player's key is kept
    check_click_grid(song["analysis"])


def test_keyfinder_export_comes_back_as_it_left(client, tmp_path):
    """A KeyFinder Player export imports with its artist, stems and click, and its mix as the original."""
    y = progression(D_MAJOR, bpm=BPM)
    path = tmp_path / "Round Trip.wav"
    audio.save(path, y, SR)
    first = client.post("/api/songs", files={"file": ("Round Trip.wav", path.read_bytes(), "audio/wav")},
                        data={"mode": "2stems", "backend": "dsp"}).json()["id"]
    client.patch(f"/api/songs/{first}", json={"artist": "Ana Ribeiro"})
    res = client.get(f"/api/songs/{first}/export", params={"format": "player"})
    name = client.get(f"/api/songs/{first}/export/player-name").json()["name"]
    second = client.post("/api/songs", files={"file": (name, res.content, "application/zip")}).json()["id"]
    song = client.get(f"/api/songs/{second}").json()
    assert song["status"] == "ready", song["error"]
    assert (song["title"], song["artist"]) == ("Round Trip", "Ana Ribeiro")
    assert sorted(song["stem_names"].values()) == ["Backing", "Click Track", "Vocals"]  # Reference → original
    assert song["analysis"]["sources"]["beats"] == "click"

    # Exported again: its own Click Track goes back, not a second one.
    again = client.get(f"/api/songs/{second}/export", params={"format": "player"}).content
    with zipfile.ZipFile(io.BytesIO(again)) as zf:
        names = sorted(n.rsplit("/", 1)[1] for n in zf.namelist())
    assert names == ["Backing.wav", "Click Track.wav", "Reference.wav", "Vocals.wav"]


def test_bad_packages_are_clear_errors(client, tmp_path):
    with zipfile.ZipFile(tmp_path / "notes.zip", "w") as zf:
        zf.writestr("readme.txt", "no audio here")
    song_id = client.post("/api/songs", files={"file": ("notes.zip", (tmp_path / "notes.zip").read_bytes(),
                                                        "application/zip")}).json()["id"]
    song = client.get(f"/api/songs/{song_id}").json()
    assert song["status"] == "error" and "no audio files" in song["error"]
    broken = ("broken.zip", b"PK\x03\x04 not a zip", "application/zip")
    song_id = client.post("/api/songs", files={"file": broken}).json()["id"]
    assert "can't read the zip" in client.get(f"/api/songs/{song_id}").json()["error"]
