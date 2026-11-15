"""Transposing audio files: change a file's key (and, if you like, its speed) and save it.

A file to transpose isn't added to the library: it's kept in ``<data>/transpose/<id>/`` with
what KeyFinder found in it (its key, keys and tempo, from the same analysis songs get, without
the stems), rendered on request at any pitch and speed, and removed after a day.
"""

from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from pathlib import Path

from . import analysis, audio, transform

KEEP_SECONDS = 24 * 3600
FORMATS = ("mp3", "wav", "m4a", "flac")
ID = re.compile(r"^[0-9a-f]{32}$")


class NotFound(KeyError):
    pass


class Transposer:
    def __init__(self, data_dir: Path):
        self.root = Path(data_dir) / "transpose"
        self.root.mkdir(parents=True, exist_ok=True)
        self.cleanup()

    def _dir(self, item_id: str) -> Path:
        if not ID.match(item_id) or not (self.root / item_id / "info.json").exists():
            raise NotFound(item_id)
        return self.root / item_id

    def get(self, item_id: str) -> dict:
        return json.loads((self._dir(item_id) / "info.json").read_text())

    def add(self, filename: str, data_path: Path) -> dict:
        """Take the file (moved from ``data_path``) and find its key and tempo."""
        self.cleanup()
        item_id = uuid.uuid4().hex
        folder = self.root / item_id
        folder.mkdir(parents=True)
        suffix = re.sub(r"[^a-z0-9.]", "", Path(filename).suffix.lower())[:8] or ".bin"
        source = folder / f"source{suffix}"
        shutil.move(str(data_path), source)
        try:
            y = audio.load(source, audio.ANALYSIS_SR)
            if y.size < 2 * audio.ANALYSIS_SR:
                raise audio.AudioError("the audio is shorter than 2 seconds")
            result = analysis.analyze_signal(y, audio.ANALYSIS_SR)
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        sections = result.get("key_sections") or []
        tags = audio.probe(source)
        info = {
            "id": item_id,
            "name": Path(filename).stem[:200] or "Untitled",
            "format": suffix.lstrip("."),
            "title": tags.get("title") or "",
            "artist": tags.get("artist") or "",
            "duration": result["duration"],
            "key": {k: v for k, v in result["key"].items() if k in ("name", "tonic", "mode", "camelot", "confidence")},
            "keys": [s["name"] for s in sections] if len(sections) > 1 else None,
            "bpm": result["bpm"],
            "tuning_cents": result["tuning_cents"],
            "created_at": time.time(),
        }
        (folder / "info.json").write_text(json.dumps(info))
        return info

    def render(self, item_id: str, semitones: int, speed: float, fmt: str) -> Path:
        """The file at ``semitones`` and ``speed``, in ``fmt``; the caller deletes it once sent."""
        if fmt not in FORMATS:
            raise ValueError(f"can't save as .{fmt}; choose {', '.join(FORMATS)}")
        folder = self._dir(item_id)
        source = next(folder.glob("source.*"))
        dest = folder / f"render-{uuid.uuid4().hex[:8]}.{fmt}"
        transform.render(source, dest, semitones=semitones, speed=speed)
        return dest

    def delete(self, item_id: str) -> None:
        shutil.rmtree(self._dir(item_id), ignore_errors=True)

    def cleanup(self) -> None:
        """Forget files added more than a day ago."""
        cutoff = time.time() - KEEP_SECONDS
        for folder in self.root.iterdir():
            try:
                if folder.stat().st_mtime < cutoff:
                    shutil.rmtree(folder, ignore_errors=True)
            except OSError:
                continue
