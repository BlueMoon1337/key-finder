"""A small on-disk job store and background worker for song processing.

Each song lives in ``<data>/songs/<id>/``:

* ``source.<ext>`` - the uploaded file
* ``song.json``    - status, progress, metadata, analysis results and stem list
* ``cover.jpg``    - embedded artwork or a video frame, when there is one
* ``stems/``       - one mp3 per stem, plus cached pitch-shifted renders

A song that arrives as stems (a MultiTracks zip, a folder of stems, a Player song) is a
"package": its stems are kept as they are, named and sorted by kind with Player's rules
(``stems.py``), instead of being separated.
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

import numpy as np
from scipy.signal import resample_poly

from . import analysis, audio, lyrics, neural, package, separation, stems

ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
ORIGINAL = "original"
MIN_SECONDS = 2
PACKAGE = "stems"  # the mode of a song that arrived as stems
# KeyFinder's separated stems by the names Player routes (Player reads "Guitar" as an electric
# guitar, "Other" goes to its Aux bus).
SEPARATED_NAMES = {
    "vocals": "Vocals", "drums": "Drums", "bass": "Bass", "guitar": "Guitar", "piano": "Piano",
    "other": "Other", "accompaniment": "Backing",
    # Choir and strings isolation (vocal_split.py, separation.split_strings).
    "lead": "Lead Vocal", "choir": "Choir", "strings": "Strings",
}


def stem_labels(song: dict) -> tuple[dict[str, str], dict[str, str]]:
    """Each stem's name and kind (one of stems.KINDS): a package's own, else by KeyFinder's names."""
    names = dict(song.get("stem_names") or {})
    kinds = dict(song.get("stem_kinds") or {})
    for sid in song.get("stems", []):
        if sid == ORIGINAL:
            continue
        names.setdefault(sid, SEPARATED_NAMES.get(sid, sid.replace("-", " ").title()))
        kinds.setdefault(sid, stems.kind_of(names[sid]))
    return names, kinds


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
        keep = ("id", "title", "artist", "cover", "status", "progress", "stage", "error", "warning", "created_at",
                "mode", "backend", "stems", "lyrics_status", "choir", "strings")
        out = {k: song.get(k) for k in keep}
        result = song.get("analysis") or {}
        if result:
            out.update(key=result["key"]["name"], camelot=result["key"]["camelot"],
                       bpm=result["bpm"], duration=result["duration"])
            sections = result.get("key_sections") or []
            if len(sections) > 1:
                out["keys"] = [s["name"] for s in sections]
            tempos = result.get("tempo_sections") or []
            if len(tempos) > 1:
                out["tempos"] = [s["bpm"] for s in tempos]
            # Every chord the song uses, at any detail level ("7:maj" is G), for the Chord Library.
            used = {(c["root"], c["quality"]) for level in (result.get("chords") or {}).values() for c in level
                    if c.get("root") is not None and c.get("quality")}
            out["chords"] = [f"{r}:{q}" for r, q in sorted(used)]
        return out

    def delete(self, song_id: str) -> None:
        shutil.rmtree(self.song_dir(song_id))

    def update_info(self, song_id: str, title: str | None = None, artist: str | None = None) -> dict:
        """Rename a song; edited fields are no longer overwritten by file tags."""
        fields: dict = {}
        song = self.get(song_id)
        edited = set(song.get("edited", []))
        if title is not None:
            if not title.strip():
                raise ValueError("title cannot be empty")
            fields["title"] = title.strip()[:200]
            edited.add("title")
        if artist is not None:
            fields["artist"] = artist.strip()[:200]
            edited.add("artist")
        return self._update(song_id, edited=sorted(edited), **fields)

    # ------------------------------------------------------------------ lyrics

    def find_lyrics(self, song_id: str, mode: str | None = None) -> dict:
        """Look up / transcribe a ready song's lyrics again (or for the first time) in the background."""
        song = self.get(song_id)
        if song["status"] != "ready":
            raise ValueError("song is still processing")
        if song.get("lyrics_status") in ("queued", "working"):
            raise ValueError("its lyrics are already being found")
        if mode is not None and mode not in lyrics.MODES:
            raise ValueError(f"unknown lyrics mode {mode!r}")
        song = self._update(song_id, lyrics_mode=mode or song.get("lyrics_mode") or "auto")
        self._queue_lyrics(song_id, force=True)
        return self.get(song_id)

    def edit_lyrics(self, song_id: str, lines: list[str]) -> dict:
        song = self.get(song_id)
        if not (song.get("lyrics") or {}).get("lines"):
            raise ValueError("this song has no lyrics to edit")
        return self._update(song_id, lyrics=lyrics.edit(song["lyrics"], [str(t)[:300] for t in lines]))

    def _queue_lyrics(self, song_id: str, force: bool = False) -> None:
        song = self.get(song_id)
        if song.get("lyrics_mode", "auto") == "off" and not force:
            self._update(song_id, lyrics_status="off")
            return
        self._update(song_id, lyrics_status="queued", lyrics_stage="Waiting", lyrics_note=None)
        if self.inline:
            self._find_lyrics(song_id)
        else:
            self._pool.submit(self._find_lyrics, song_id)

    def _vocals(self, song: dict):
        """A loader for the vocals Whisper should hear: the lead vocal stem(s), else the whole song."""
        folder = self.song_dir(song["id"]) / "stems"
        names, kinds = stem_labels(song)
        voices = [s for s in song["stems"] if kinds.get(s) == "vocals"]
        lead = [s for s in voices if re.search(r"lead|^vocals?$|^vox$", names.get(s, s), re.IGNORECASE)]
        chosen = lead or voices or [ORIGINAL]

        def load() -> np.ndarray:
            parts = [audio.load(folder / f"{s}.mp3", lyrics.SR) for s in chosen]
            n = max(p.size for p in parts)
            return np.sum([np.pad(p, (0, n - p.size)) for p in parts], axis=0).astype(np.float32)
        return load

    def _find_lyrics(self, song_id: str) -> None:
        try:
            song = self._update(song_id, lyrics_status="working", lyrics_stage="Looking up the lyrics",
                                lyrics_progress=0.0)
            mode = song.get("lyrics_mode") or "auto"
            transcribing = mode == "auto" and lyrics.available()
            last = [0.0]

            def progress(fraction: float) -> None:
                if fraction - last[0] >= 0.02:
                    last[0] = fraction
                    self._update(song_id, lyrics_stage="Listening to the vocals", lyrics_progress=round(fraction, 3))

            def on_download() -> None:
                self._update(song_id, lyrics_stage=f"Downloading the lyrics model (first time only, about "
                                                   f"{lyrics.MODEL_MB / 1000:.1f} GB)")

            def should_stop() -> bool:
                return not (self.root / song_id / "song.json").exists()

            if transcribing:
                self._update(song_id, lyrics_stage="Looking up the lyrics, then listening to the vocals")
            duration = (song.get("analysis") or {}).get("duration") or 0.0
            try:
                found = lyrics.find(song["title"], song.get("artist", ""), duration,
                                    self._vocals(song) if transcribing else None, mode,
                                    progress, should_stop, on_download)
            except lyrics.ModelUnavailable as exc:
                found = lyrics.find(song["title"], song.get("artist", ""), duration, None, "online")
                found["note"] = str(exc)
            self._update(song_id, lyrics=found if found["lines"] else None,
                         lyrics_status="ready" if found["lines"] else "none",
                         lyrics_stage=None, lyrics_note=found.get("note"))
        except (lyrics.Cancelled, SongNotFound):
            pass
        except Exception as exc:  # noqa: BLE001 - report it on the song; the song itself is fine
            traceback.print_exc()
            try:
                self._update(song_id, lyrics_status="failed", lyrics_stage=None, lyrics_note=str(exc)[:500])
            except SongNotFound:
                pass

    def scale_tempo(self, song_id: str, factor: float) -> dict:
        """Double or halve a ready song's tempo (when the beat tracker counted half or double time)."""
        song = self.get(song_id)
        if song["status"] != "ready" or not song.get("analysis"):
            raise ValueError("song is still processing")
        return self._update(song_id, analysis=analysis.scale_tempo(song["analysis"], factor))

    def cover_path(self, song_id: str) -> Path:
        path = self.song_dir(song_id) / "cover.jpg"
        if not path.exists():
            raise SongNotFound(f"{song_id}/cover")
        return path

    def stem_path(self, song_id: str, stem: str) -> Path:
        song = self.get(song_id)
        if stem not in song.get("stems", []):
            raise SongNotFound(f"{song_id}/{stem}")
        return self.song_dir(song_id) / "stems" / f"{stem}.mp3"

    # ------------------------------------------------------------------ jobs

    @staticmethod
    def check_options(mode: str, backend: str, choir: bool = False, strings: bool = False) -> str | None:
        """Validate separation options; returns the backend that will run (None for no separation)."""
        if mode == "none":
            return None
        if mode not in separation.MODES:
            raise ValueError(f"unknown separation mode {mode!r}")
        resolved = separation.choose_backend(backend, mode)
        separation.check_extras(resolved, choir, strings)
        return resolved

    def create(self, filename: str, data_path: Path, mode: str = "4stems", backend: str = "auto",
               package_folder: Path | None = None, lyrics_mode: str = "auto",
               choir: bool = False, strings: bool = False) -> dict:
        """Register an uploaded file (moved from ``data_path``) and queue processing.

        A zip, or ``package_folder`` (a folder of stems, read where it is), is a package of stems.
        """
        is_package = package_folder is not None or Path(filename).suffix.lower() == ".zip"
        choir, strings = (bool(choir), bool(strings)) if not is_package and mode != "none" else (False, False)
        resolved = "package" if is_package else self.check_options(mode, backend, choir, strings)
        song_id = uuid.uuid4().hex
        folder = self.root / song_id
        (folder / "stems").mkdir(parents=True)
        if package_folder is None:
            suffix = re.sub(r"[^a-z0-9.]", "", Path(filename).suffix.lower())[:8] or ".bin"
            source = folder / f"source{suffix}"
            shutil.move(str(data_path), source)
        # A folder's name is all name: "Song-Album-Ab-63.00bpm" has no extension to take off.
        source_name = package_folder.name if package_folder is not None else Path(filename).stem
        title = source_name.strip() or "Untitled"
        song = {
            "id": song_id, "title": title[:200], "artist": "", "cover": False, "edited": [],
            "source": source.name if package_folder is None else None,
            "package_folder": str(package_folder) if package_folder is not None else None,
            "source_name": source_name[:200],
            "mode": PACKAGE if is_package else mode, "backend": resolved, "requested_backend": backend,
            "choir": choir, "strings": strings,
            "warning": None,
            "status": "queued", "stage": "Waiting", "progress": 0.0, "error": None,
            "stems": [], "analysis": None,
            # Lyrics (lyrics.py): found after the song is ready, so it can be played meanwhile.
            "lyrics_mode": lyrics_mode if lyrics_mode in lyrics.MODES else "auto",
            "lyrics": None, "lyrics_status": "waiting", "lyrics_stage": None, "lyrics_note": None,
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
            if song["mode"] == PACKAGE:
                self._process_package(song_id, song)
                return
            folder = self.song_dir(song_id)
            source = folder / song["source"]
            stems_dir = folder / "stems"

            self._read_metadata(song_id, source)
            y = audio.load(source, audio.ANALYSIS_SR)
            if y.size < MIN_SECONDS * audio.ANALYSIS_SR:
                seconds = y.size / audio.ANALYSIS_SR
                raise audio.AudioError(f"the audio is only {seconds:.1f} s long; songs need at least {MIN_SECONDS} s")
            self._update(song_id, stage="Detecting key, tempo and chords", progress=0.15)
            result = analysis.analyze_signal(y, audio.ANALYSIS_SR)
            self._update(song_id, analysis=result, progress=0.35)

            full = audio.load(source, audio.SEPARATION_SR, mono=False)
            audio.save(stems_dir / f"{ORIGINAL}.mp3", full, audio.SEPARATION_SR)
            stems = [ORIGINAL]
            if song["mode"] != "none":
                separated, sr = self._separate(song_id, song, source)
                self._update(song_id, stage="Reading the chords from the stems", progress=0.85)
                improved = analysis.improve_with_stems(result, separated, sr)
                if improved is not result:
                    result = improved
                    self._update(song_id, analysis=result)
                self._update(song_id, stage="Encoding stems", progress=0.87)
                for name, data in separated.items():
                    audio.save(stems_dir / f"{name}.mp3", data, sr)
                    stems.append(name)
            self._update(song_id, status="ready", stage="Ready", progress=1.0, stems=stems)
            self._queue_lyrics(song_id)
        except neural.Cancelled:
            pass  # deleted while separating
        except Exception as exc:  # noqa: BLE001 - report any failure on the song itself
            traceback.print_exc()
            try:
                self._update(song_id, status="error", stage="Failed", error=str(exc)[:2000])
            except SongNotFound:
                pass  # deleted while processing

    def _process_package(self, song_id: str, song: dict) -> None:
        """Read a package's stems as they are: no separation, the analysis from the stems."""
        folder = self.song_dir(song_id)
        stems_dir = folder / "stems"
        unpacked = folder / "package"
        self._update(song_id, stage="Reading the stems", progress=0.05)
        source = Path(song["package_folder"]) if song.get("package_folder") else folder / song["source"]
        try:
            pkg = package.unpack(source, unpacked, song["source_name"])
        finally:
            if not song.get("package_folder"):
                source.unlink(missing_ok=True)  # the zip: its stems are out now
        fields: dict = {}
        for name in ("title", "artist"):
            if pkg.get(name) and name not in song.get("edited", []):
                fields[name] = str(pkg[name])[:200]
        if pkg["artwork"]:
            fields["cover"] = audio.extract_cover(unpacked / pkg["artwork"], folder / "cover.jpg")
        self._update(song_id, **fields)

        sr, half = audio.SEPARATION_SR, audio.ANALYSIS_SR
        ids: list[str] = []
        used: set[str] = {ORIGINAL}
        names, kinds = {}, {}
        sums: dict[str, np.ndarray | None] = {"full": None, "full_mono": None, "harmonic": None}
        click = reference = None

        def add(key: str, y: np.ndarray) -> None:
            total = sums[key]
            if total is None:
                sums[key] = y.copy()
                return
            n = max(total.shape[-1], y.shape[-1])
            pad = lambda a: np.pad(a, [(0, 0)] * (a.ndim - 1) + [(0, n - a.shape[-1])])  # noqa: E731
            sums[key] = pad(total) + pad(y)

        for i, stem in enumerate(pkg["stems"]):
            self._update(song_id, stage=f"Reading the stems: {stem['name']}",
                         progress=round(0.08 + 0.5 * i / len(pkg["stems"]), 3))
            y = audio.load(unpacked / stem["file"], sr, mono=False)
            mono = resample_poly(y.mean(axis=0), half, sr).astype(np.float32)
            kind = stem["kind"]
            if kind == "reference" and reference is None:
                audio.save(stems_dir / f"{ORIGINAL}.mp3", y, sr)
                reference = mono
                continue
            sid = stems.stem_id(stem["name"], used)
            audio.save(stems_dir / f"{sid}.mp3", y, sr)
            ids.append(sid)
            names[sid], kinds[sid] = stem["name"], kind
            if kind == "click" and click is None:
                click = mono
            if kind not in stems.NOT_MUSIC:
                add("full", y)
                add("full_mono", mono)
            if kind in stems.HARMONIC:
                add("harmonic", mono)
        shutil.rmtree(unpacked, ignore_errors=True)

        full = sums["full_mono"] if sums["full_mono"] is not None else reference
        if full is None:
            raise audio.AudioError("it has only a click or guide track, no music to analyse")
        if full.size < MIN_SECONDS * half:
            seconds = full.size / half
            raise audio.AudioError(f"the audio is only {seconds:.1f} s long; songs need at least {MIN_SECONDS} s")
        if reference is None:
            mix = sums["full"]
            peak = float(np.abs(mix).max()) if mix.size else 0.0
            audio.save(stems_dir / f"{ORIGINAL}.mp3", mix * (0.98 / peak if peak > 0.98 else 1.0), sr)

        self._update(song_id, stage="Detecting key, tempo and chords", progress=0.65)
        result = analysis.analyze_package(full, sums["harmonic"], click, half,
                                          key_hint=stems.parse_key(str(pkg.get("key") or "")),
                                          bpm_hint=float(pkg["bpm"]) if pkg.get("bpm") else None)
        warning = None
        if pkg["skipped"]:
            warning = "Left out: " + "; ".join(f"{s['name']} ({s['reason']})" for s in pkg["skipped"])
        self._update(song_id, status="ready", stage="Ready", progress=1.0, analysis=result,
                     stems=[ORIGINAL, *ids], stem_names=names, stem_kinds=kinds, warning=warning,
                     package={"named_by": pkg["named_by"], "key": pkg.get("key"), "bpm": pkg.get("bpm")})
        self._queue_lyrics(song_id)

    def _separate(self, song_id: str, song: dict, source: Path):
        """Separate with the song's backend, reporting progress between 45 % and 85 %."""
        backend = song["backend"]
        label = "Demucs" if backend == "demucs" else "the fast separator"
        separating = f"Separating stems with {label}"
        self._update(song_id, stage=separating, progress=0.45)
        last = [0.0]
        downloading = [False]

        def progress(fraction: float) -> None:
            if downloading[0]:  # the model arrived and separation has begun
                downloading[0] = False
                try:
                    self._update(song_id, stage=separating)
                except SongNotFound:
                    pass
            value = 0.45 + 0.4 * fraction
            if value - last[0] >= 0.01:  # one write per percent is plenty
                last[0] = value
                try:
                    self._update(song_id, progress=round(value, 3))
                except SongNotFound:
                    pass  # deleted: should_stop() ends the separation

        def should_stop() -> bool:
            return not (self.root / song_id / "song.json").exists()

        def on_download() -> None:
            downloading[0] = True
            self._update(song_id, stage="Downloading the Demucs model (first time only)")

        def on_choir_download() -> None:
            downloading[0] = True
            self._update(song_id, stage="Downloading the choir model (first time only)")

        choir, strings = bool(song.get("choir")), bool(song.get("strings"))
        if choir or strings:
            what = " and ".join(w for w, on in (("the choir", choir), ("strings", strings)) if on)
            separating = f"Separating stems with Demucs, then {what}"
            self._update(song_id, stage=separating)
        notes: dict = {}
        try:
            separated = separation.separate(source, song["mode"], backend, progress, should_stop, on_download,
                                            choir=choir, strings=strings, on_choir_download=on_choir_download,
                                            notes=notes)
        except neural.ModelUnavailable as exc:
            # Asked for "best available" and offline the first time: use the fast separator now.
            # The fast separator can't do the choir or strings, so those wait for Demucs.
            if song.get("requested_backend", "auto") != "auto" or song["mode"] not in separation.DSP_MODES \
                    or choir or strings:
                raise
            self._update(song_id, backend="dsp", stage="Separating stems with the fast separator",
                         warning=f"{exc} The fast separator was used instead.")
            separated = separation.separate(source, song["mode"], "dsp", progress, should_stop)
        if should_stop():
            raise neural.Cancelled()
        if notes:
            self._update(song_id, separation_notes=notes)
        return separated

    def _read_metadata(self, song_id: str, source: Path) -> None:
        """Take title/artist from the file's tags and pull out cover art or a video frame."""
        meta = audio.probe(source)
        song = self.get(song_id)
        fields = {}
        for name in ("title", "artist"):
            if meta.get(name) and name not in song.get("edited", []):
                fields[name] = meta[name][:200]
        cover = self.song_dir(song_id) / "cover.jpg"
        if meta.get("cover"):
            fields["cover"] = audio.extract_cover(source, cover)
        elif meta.get("video"):
            fields["cover"] = audio.extract_cover(source, cover, at=min(1.0, meta.get("duration", 0) / 3))
        if fields:
            self._update(song_id, **fields)

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
            elif song.get("lyrics_status") in ("queued", "working"):
                self._queue_lyrics(song["id"], force=True)  # the song is fine; find its lyrics again

    def shutdown(self) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)
