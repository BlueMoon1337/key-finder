"""Exports a song as a stems package for Player (github.com/BlueMoon1337/Player).

Player imports MultiTracks.com downloads, so the package follows their layout:

* a zip named ``Title-Album-Key-BPMbpm.zip``, which is where Player reads the key and tempo.
  KeyFinder has no album and puts the artist in its place; the WAVs' software tag (``ISFT``
  "KeyFinder") tells Player to read it as the artist;
* ``MultiTracks/`` holding one WAV per stem. Each WAV also carries the title, artist and
  software (``LIST/INFO``), the tempo and meter (``acid``), the beat map (``bmap``: where bar 1
  falls, the tempo changes and the time signature changes, as JSON; see ``_bmap``) and, when the
  song changes key or tempo, a cue marker at each change, which Player turns into song sections;
* ``Click Track.wav``, clicked on the beats KeyFinder found and accented on the downbeats.
  Player plays a stem by that name as the song's click, so the click follows the
  performance, which a click generated from one BPM can't. A song that came with its own
  click (a MultiTracks download) keeps that one instead, and its other stems their names;
* ``Album.jpg``, the cover, when there is one.

Pitch and speed apply to every stem, the click and the markers, so a song exported two
semitones down at 90 % arrives in Player in its new key and tempo.
"""

from __future__ import annotations

import json
import re
import struct
import zipfile
from pathlib import Path

import numpy as np

from . import audio, key, tempo, transform
from .jobs import ORIGINAL, stem_labels

SR = transform.SR
CLICK_STEM = "Click Track"
REFERENCE = "Reference"  # the original mix; Player hides it unless its Reference Track setting is on
FULL_MIX = "Song"  # the original, when the song wasn't split


def player_key(tonic: int, mode: str, semitones: int = 0) -> str:
    """A key as MultiTracks names write it: "Ab", "F#m"."""
    names = key.MAJOR_TONIC if mode == "major" else key.MINOR_TONIC
    return names[(tonic + semitones) % 12] + ("m" if mode == "minor" else "")


def _name_part(text: str) -> str:
    # A hyphen would end the title early (Player splits the name at hyphens), and some
    # characters can't be in a file name on Windows or macOS.
    text = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", text).replace("-", "–")
    return re.sub(r"\s+", " ", text).strip(" .")


def package_name(song: dict, semitones: int = 0, speed: float = 1.0) -> str:
    """``Title-Artist-Key-BPMbpm``, the zip's name without ``.zip``."""
    result = song["analysis"]
    k = result["key"]
    title = _name_part(song.get("title") or "") or "Untitled"
    artist = _name_part(song.get("artist") or "") or "KeyFinder"
    return f"{title}-{artist}-{player_key(k['tonic'], k['mode'], semitones)}-{result['bpm'] * speed:.2f}bpm"


def click_track(beats: list[float], downbeats: list[float], frames: int, sr: int = SR) -> np.ndarray:
    """A mono click: a short high tick on each downbeat, a lower one on the other beats."""
    y = np.zeros(frames, dtype=np.float32)
    length = int(0.03 * sr)
    t = np.arange(length) / sr
    envelope = np.exp(-t / 0.006)
    accent = (0.9 * np.sin(2 * np.pi * 1760 * t) * envelope).astype(np.float32)
    tick = (0.6 * np.sin(2 * np.pi * 1320 * t) * envelope).astype(np.float32)
    bars = np.asarray(sorted(downbeats))
    for b in beats:
        start = int(round(b * sr))
        if not 0 <= start < frames:
            continue
        on_bar = bars.size and np.abs(bars - b).min() < 0.02
        sound = accent if on_bar else tick
        end = min(frames, start + length)
        y[start:end] += sound[: end - start]
    return y


def _chunk(cid: bytes, body: bytes) -> bytes:
    return cid + struct.pack("<I", len(body)) + body + (b"\0" if len(body) % 2 else b"")


def _info(title: str, artist: str) -> bytes:
    fields = b""
    for cid, text in ((b"INAM", title), (b"IART", artist), (b"ISFT", "KeyFinder")):
        if text:
            fields += _chunk(cid, text.encode("utf-8") + b"\0")
    return _chunk(b"LIST", b"INFO" + fields)


def _acid(bpm: float, beats: int, per_bar: int = 4) -> bytes:
    # flags, root note, two unused fields, number of beats, meter denominator and numerator, tempo.
    return _chunk(b"acid", struct.pack("<IHHfIHHf", 0, 60, 0x8000, 0.0, beats, 4, per_bar, bpm))


def _bmap(beats: list[float], downbeats: list[float], beats_per_bar: int) -> bytes:
    """The beat map Player reads tempo and time signature changes from (its "bmap" chunk)."""
    m = tempo.beat_map(beats, downbeats, beats_per_bar)
    body = {
        "version": 1,
        "offset": m["offset"],
        "tempos": [[t["start"], t["bpm"]] for t in m["tempos"]],
        "meters": [[x["start"], x["beats"], 4] for x in m["meters"]],
    }
    return _chunk(b"bmap", json.dumps(body, separators=(",", ":")).encode("utf-8"))


def _cues(markers: list[tuple[int, str]]) -> bytes:
    if not markers:
        return b""
    points = b"".join(struct.pack("<II4sIII", i + 1, frame, b"data", 0, 0, frame)
                      for i, (frame, _) in enumerate(markers))
    labels = b"".join(_chunk(b"labl", struct.pack("<I", i + 1) + text.encode("utf-8") + b"\0")
                      for i, (_, text) in enumerate(markers))
    return _chunk(b"cue ", struct.pack("<I", len(markers)) + points) + _chunk(b"LIST", b"adtl" + labels)


def wav_bytes_header(frames: int, channels: int, sr: int, metadata: bytes) -> bytes:
    """A 16-bit PCM WAV header with ``metadata`` chunks before the data chunk."""
    block = channels * 2
    fmt = _chunk(b"fmt ", struct.pack("<HHIIHH", 1, channels, sr, sr * block, block, 16))
    data_size = frames * block
    riff_size = 4 + len(fmt) + len(metadata) + 8 + data_size + (data_size % 2)
    return b"RIFF" + struct.pack("<I", riff_size) + b"WAVE" + fmt + metadata + b"data" + struct.pack("<I", data_size)


def _write_wav(zf: zipfile.ZipFile, arcname: str, y: np.ndarray, metadata: bytes) -> None:
    y = np.atleast_2d(y)
    pcm = (np.clip(y, -1.0, 1.0) * 32767.0).round().astype("<i2").T  # interleaved frames
    with zf.open(arcname, "w") as out:
        out.write(wav_bytes_header(pcm.shape[0], pcm.shape[1], SR, metadata))
        for start in range(0, pcm.shape[0], 1 << 16):
            out.write(pcm[start:start + (1 << 16)].tobytes())
        if pcm.size % 2:
            out.write(b"\0")


def build(song: dict, folder: Path, dest: Path, semitones: int = 0, speed: float = 1.0) -> Path:
    """Write the package for the song in ``folder`` to ``dest`` (a .zip)."""
    transform._check(semitones, speed)
    result = song["analysis"]
    name = package_name(song, semitones, speed)
    parts = [s for s in song["stems"] if s != ORIGINAL]
    names, kinds = stem_labels(song)
    files, used = [], set()
    for sid, label in [(s, names[s]) for s in parts] + [(ORIGINAL, REFERENCE if parts else FULL_MIX)]:
        label = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", label).strip() or "Stem"
        unique, n = label, 2
        while unique.lower() in used:
            unique, n = f"{label} {n}", n + 1
        used.add(unique.lower())
        files.append((sid, unique))
    own_click = any(kinds.get(s) == "click" for s in parts)

    beats = [b / speed for b in result["beats"]]
    downbeats = [d / speed for d in result["downbeats"]]
    sections = result.get("key_sections") or []
    # A section in Player at each key change and each tempo change; one that comes within a
    # bar of another (a medley's next song often changes both) shares its marker.
    changes: list[tuple[float, int, str]] = []  # (time, key before tempo, label)
    if len(sections) > 1:
        changes += [(s["start"], 0, key.key_name((s["tonic"] + semitones) % 12, s["mode"])) for s in sections]
    tempos = result.get("tempo_sections") or []
    if len(tempos) > 1:
        changes += [(s["start"], 1, f"{round(s['bpm'] * speed)} BPM") for s in tempos]
    bar = 4 * 60.0 / result["bpm"]
    merged: list[tuple[float, list]] = []
    for t, kind, label in sorted(changes):
        if merged and t - merged[-1][0] < bar:
            merged[-1][1].append((kind, label))
        else:
            merged.append((t, [(kind, label)]))
    markers = [(int(round(t / speed * SR)), " · ".join(label for _, label in sorted(labels))[:32])
               for t, labels in merged]
    if markers:
        markers[0] = (0, markers[0][1])
    metadata = (_info(song.get("title") or "", song.get("artist") or "")
                + _acid(round(result["bpm"] * speed, 2), len(beats), result.get("beats_per_bar", 4))
                + _bmap(beats, downbeats, result.get("beats_per_bar", 4))
                + _cues(markers))

    # Every stem and the click the same length, so they line up to the sample in Player: decoding
    # and time-stretching each MP3 can leave a few milliseconds more or less.
    frames = int(round(result["duration"] / speed * SR))
    tmp = dest.with_name(dest.stem + ".partial.zip")
    try:
        # Stored, not deflated: audio barely compresses, and Player reads stored zips fastest.
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
            for stem, label in files:
                y = transform.shift(audio.load(folder / "stems" / f"{stem}.mp3", SR, mono=False), semitones, speed)
                y = np.pad(y, ((0, 0), (0, max(0, frames - y.shape[1]))))[:, :frames]
                _write_wav(zf, f"{name}/MultiTracks/{label}.wav", y, metadata)
            if not own_click:
                click = click_track(beats, downbeats, frames)
                _write_wav(zf, f"{name}/MultiTracks/{CLICK_STEM}.wav", click, metadata)
            cover = folder / "cover.jpg"
            if cover.exists():
                zf.write(cover, f"{name}/Album.jpg")
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)
    return dest
