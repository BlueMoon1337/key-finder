"""A small on-disk job store and background worker for song processing.

Each song lives in ``<data>/songs/<id>/``:

* ``source.<ext>`` - the uploaded file
* ``song.json``    - status, progress, analysis results and stem list
* ``stems/``       - one mp3 per stem, plus cached pitch-shifted renders
"""

from __future__ import annotations

import json
import re
import shutil
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import analysis, audio, separation

ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
ORIGINAL = "original"


class SongNotFound(KeyError):
    pass


class JobStore:
    def __init__(self, root: str | Path, workers: int = 1, inline: bool = False):
        self.root = Path(root) / "songs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.inline = inline
        self._lock = threading.RLock()
        self._pool = None if inline else ThreadPoolExecutor(max_workers=workers, thread_name_prefix="keyfinder")
        self._recover()

    # ------------------------------------------------------------------ storage

    def song_dir(self, song_id: str) -> Path:
        if not ID_PATTERN.match(song_id):
            raise SongNotFound(song_id)
        path = self.root / song_id
        if not path.is_dir():
            raise SongNotFound(song_id)
        return path

    def get(self, song_id: str) -> dict:
        path = self.song_dir(song_id) / "song.json"
        with self._lock:
            try:
                return json.loads(path.read_text())
            except FileNotFoundError as exc:
                raise SongNotFound(song_id) from exc

    def _update(self, song_id: str, **fields) -> dict:
        with self._lock:
            song = self.get(song_id)
            song.update(fields)
            song["updated_at"] = time.time()
            path = self.song_dir(song_id) / "song.json"
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(song))
            tmp.replace(path)
            return song

    def list(self) -> list[dict]:
        songs = []
        for path in self.root.iterdir():
            try:
                songs.append(self.summary(self.get(path.name)))
            except (SongNotFound, json.JSONDecodeError):
                continue
        return sorted(songs, key=lambda s: s["created_at"], reverse=True)

    @staticmethod
    def summary(song: dict) -> dict:
        keep = ("id", "title", "status", "progress", "stage", "error", "created_at", "mode", "backend", "stems")
        out = {k: song.get(k) for k in keep}
        result = song.get("analysis") or {}
        if result:
            out.update(key=result["key"]["name"], camelot=result["key"]["camelot"],
                       bpm=result["bpm"], duration=result["duration"])
        return out

    def delete(self, song_id: str) -> None:
        shutil.rmtree(self.song_dir(song_id))

    def stem_path(self, song_id: str, stem: str) -> Path:
        song = self.get(song_id)
        if stem not in song.get("stems", []):
            raise SongNotFound(f"{song_id}/{stem}")
        return self.song_dir(song_id) / "stems" / f"{stem}.mp3"

    # ------------------------------------------------------------------ jobs

    def create(self, filename: str, data_path: Path, mode: str = "4stems", backend: str = "auto") -> dict:
        """Register an uploaded file (moved from ``data_path``) and queue processing."""
        if mode != "none" and mode not in separation.MODES:
            raise ValueError(f"unknown separation mode {mode!r}")
        resolved = separation.choose_backend(backend, mode) if mode != "none" else None
        song_id = uuid.uuid4().hex
        folder = self.root / song_id
        (folder / "stems").mkdir(parents=True)
        suffix = re.sub(r"[^a-z0-9.]", "", Path(filename).suffix.lower())[:8] or ".bin"
        source = folder / f"source{suffix}"
        shutil.move(str(data_path), source)
        title = Path(filename).stem.strip() or "Untitled"
        song = {
            "id": song_id, "title": title[:200], "source": source.name,
            "mode": mode, "backend": resolved,
            "status": "queued", "stage": "Waiting", "progress": 0.0, "error": None,
            "stems": [], "analysis": None,
            "created_at": time.time(), "updated_at": time.time(),
        }
        (folder / "song.json").write_text(json.dumps(song))
        if self.inline:
            self._process(song_id)
        else:
            self._pool.submit(self._process, song_id)
        return self.get(song_id)

    def _process(self, song_id: str) -> None:
        try:
            song = self._update(song_id, status="processing", stage="Decoding", progress=0.05)
            folder = self.song_dir(song_id)
            source = folder / song["source"]
            stems_dir = folder / "stems"

            y = audio.load(source, audio.ANALYSIS_SR)
            self._update(song_id, stage="Detecting key, tempo and chords", progress=0.15)
            result = analysis.analyze_signal(y, audio.ANALYSIS_SR)
            self._update(song_id, analysis=result, progress=0.35)

            full = audio.load(source, audio.SEPARATION_SR, mono=False)
            audio.save(stems_dir / f"{ORIGINAL}.mp3", full, audio.SEPARATION_SR)
            stems = [ORIGINAL]
            if song["mode"] != "none":
                self._update(song_id, stage=f"Separating stems ({song['backend']})", progress=0.45)
                separated, sr = separation.separate(source, song["mode"], song["backend"])
                self._update(song_id, stage="Encoding stems", progress=0.85)
                for name, data in separated.items():
                    audio.save(stems_dir / f"{name}.mp3", data, sr)
                    stems.append(name)
            self._update(song_id, status="ready", stage="Ready", progress=1.0, stems=stems)
        except Exception as exc:  # noqa: BLE001 - report any failure on the song itself
            traceback.print_exc()
            try:
                self._update(song_id, status="error", stage="Failed", error=str(exc)[:2000])
            except SongNotFound:
                pass  # deleted while processing

    def _recover(self) -> None:
        """Mark songs interrupted by a restart as failed so they do not spin forever."""
        for path in self.root.iterdir():
            try:
                song = self.get(path.name)
            except (SongNotFound, json.JSONDecodeError):
                continue
            if song["status"] in ("queued", "processing"):
                self._update(song["id"], status="error", stage="Failed",
                             error="Processing was interrupted by a server restart; please re-upload.")

    def shutdown(self) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)
