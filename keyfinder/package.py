"""Songs that arrive as stems: MultiTracks.com zips, folders of stems, Player song folders.

``unpack`` copies or extracts a package's stems and cover picture into a song's folder and
says what it found: each stem's name and kind (by Player's rules, ``stems.py``), and what the
package says about the song (title, artist, key, BPM). KeyFinder's own Player exports are
packages too, so they come back with their stems and Click Track.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

from . import audio, stems

MAX_STEMS = 64


class PackageError(ValueError):
    pass


def is_package(path: Path) -> bool:
    return path.is_dir() or path.suffix.lower() == ".zip"


def _player_song(folder: Path) -> dict | None:
    """A Player song folder's song.json (title, key, BPM and its stems by name), if it is one."""
    try:
        rec = json.loads((folder / "song.json").read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(rec, dict) or rec.get("version") != 1 or not isinstance(rec.get("stems"), list):
        return None
    return rec


def _from_tags(paths: list[Path]) -> dict:
    """Title and artist from the stems' tags (DAW exports and KeyFinder's write them)."""
    for path in paths:
        meta = audio.probe(path)
        if meta.get("title") or meta.get("artist"):
            return meta
    return {}


def unpack(source: Path, dest: Path, source_name: str | None = None) -> dict:
    """Copy (folder) or extract (zip) ``source``'s stems and cover into ``dest``; describe them.

    Returns ``{"title", "artist", "key", "bpm", "stems": [{"file", "name", "kind"}], "artwork",
    "skipped"}``; ``file`` and ``artwork`` are relative to ``dest``.
    """
    dest.mkdir(parents=True, exist_ok=True)
    name = source_name or (source.stem if source.suffix.lower() == ".zip" else source.name)
    record = _player_song(source) if source.is_dir() else None
    skipped: list[dict] = []

    if source.is_dir():
        if record:
            listed = [s for s in record["stems"] if isinstance(s, dict) and isinstance(s.get("file"), str)]
            files = [s["file"] for s in listed if (source / s["file"]).is_file()]
            names = {s["file"]: str(s.get("name") or s["file"]) for s in listed}
            art = record.get("artwork") if isinstance(record.get("artwork"), str) else None
            picked = {"stems": files, "artwork": art if art and (source / art).is_file() else None}
        else:
            paths = [p.relative_to(source).as_posix() for p in sorted(source.rglob("*")) if p.is_file()]
            picked = stems.pick_files(paths)
            names = {}

        def copy(rel: str, target: Path) -> None:
            shutil.copyfile(source / rel, target)
    else:
        try:
            zf = zipfile.ZipFile(source)
        except (OSError, zipfile.BadZipFile) as exc:
            raise PackageError(f"can't read the zip: {exc}") from exc
        entries = {i.filename: i for i in zf.infolist() if not i.is_dir()}
        picked = stems.pick_files(list(entries))
        names = {}

        def copy(rel: str, target: Path) -> None:
            info = entries[rel]
            if info.flag_bits & 0x1:
                raise PackageError("it's encrypted")
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out, 1 << 20)  # zipfile checks the CRC at the end

    if not picked["stems"]:
        raise PackageError("there are no audio files in it")
    if len(picked["stems"]) > MAX_STEMS:
        raise PackageError(f"it has {len(picked['stems'])} audio files; KeyFinder takes up to {MAX_STEMS} stems")

    display = stems.display_names(picked["stems"])
    found = []
    try:
        for i, (rel, label) in enumerate(zip(picked["stems"], display, strict=True)):
            label = names.get(rel, label)
            target = dest / f"{i:02d}{Path(rel).suffix.lower()}"
            try:
                copy(rel, target)
            except (OSError, zipfile.BadZipFile, PackageError) as exc:
                target.unlink(missing_ok=True)
                skipped.append({"name": label, "reason": str(exc) or "couldn't be read"})
                continue
            found.append({"file": target.name, "name": label, "kind": stems.kind_of(label), "source": rel})
        artwork = None
        if picked["artwork"]:
            target = dest / f"artwork{Path(picked['artwork']).suffix.lower()}"
            try:
                copy(picked["artwork"], target)
                artwork = target.name
            except (OSError, zipfile.BadZipFile, PackageError):
                target.unlink(missing_ok=True)
    finally:
        if not source.is_dir():
            zf.close()
    if not found:
        raise PackageError("none of its audio files could be read: " + "; ".join(s["reason"] for s in skipped))

    if record:
        click_id = record.get("clickStem")
        click_files = {s["file"] for s in record["stems"] if isinstance(s, dict) and s.get("id") == click_id}
        for stem in found:
            if stem["source"] in click_files:
                stem["kind"] = "click"
        info = {"title": record.get("title"), "artist": record.get("artist"), "key": record.get("key"),
                "bpm": record.get("bpm")}
        named_by = "player"
    else:
        parsed = stems.parse_song_name(name)
        tags = _from_tags([dest / s["file"] for s in found if s["kind"] not in stems.NOT_MUSIC][:4])
        from_keyfinder = tags.get("encoder", "") == "KeyFinder"
        album = parsed.get("album")
        info = {
            "title": parsed["title"] if album else (tags.get("title") or parsed["title"]),
            # KeyFinder's exports put the artist where MultiTracks put the album.
            "artist": tags.get("artist") or (album if from_keyfinder and album != "KeyFinder" else ""),
            "key": parsed.get("key"),
            "bpm": parsed.get("bpm"),
        }
        named_by = "keyfinder" if from_keyfinder else ("multitracks" if album else "folder")
    return {**info, "stems": found, "artwork": artwork, "skipped": skipped, "named_by": named_by}
