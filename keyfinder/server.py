"""HTTP API, plus the built web UI when it is present.

Two ways to run it:

* ``keyfinder serve`` - a local web app for a browser (uploads over HTTP).
* the desktop engine (``keyfinder.engine``) - started by the Electron app with
  a per-launch token. Every API call must carry that token, which keeps other
  programs and web pages on the computer out, and only then may songs be
  imported straight from a path on disk.
"""

from __future__ import annotations

import hmac
import os
import shutil
import tempfile
import threading
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from . import (
    ENGINE_API,
    __version__,
    audio,
    key,
    lyrics,
    neural,
    player_export,
    remote,
    separation,
    stems,
    tempo,
    transform,
)
from .jobs import ORIGINAL, JobStore, SongNotFound, stem_labels
from .transposer import FORMATS as TRANSPOSE_FORMATS
from .transposer import NotFound, Transposer

MAX_UPLOAD_BYTES = int(os.environ.get("KEYFINDER_MAX_UPLOAD_MB", "500")) * 1024 * 1024
# Zips of stems (MultiTracks downloads run to a few GB) imported from disk in the desktop app.
MAX_PACKAGE_BYTES = int(os.environ.get("KEYFINDER_MAX_PACKAGE_MB", "8192")) * 1024 * 1024
TOKEN_HEADER = "X-KeyFinder-Token"
NO_UI = """<!doctype html><meta charset="utf-8"><title>KeyFinder</title>
<body style="font:16px system-ui;background:#000;color:#eee;padding:40px">
<h1>KeyFinder engine is running</h1>
<p>The web interface hasn't been built. Run <code>npm install &amp;&amp; npm run build</code> in the repository,
or <code>npm run dev:web</code> while working on it.</p>"""


def default_ui_dir() -> Path | None:
    """The built UI: $KEYFINDER_UI_DIR, else the repository's dist/ folder."""
    env = os.environ.get("KEYFINDER_UI_DIR")
    candidates = [Path(env)] if env else [Path(__file__).resolve().parent.parent / "dist"]
    return next((p for p in candidates if (p / "index.html").is_file()), None)


def create_app(data_dir: str | Path | None = None, inline: bool = False, token: str | None = None,
               ui_dir: Path | None = None, models_dir: Path | None = None) -> FastAPI:
    data_dir = Path(data_dir or os.environ.get("KEYFINDER_DATA", "data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    # Demucs weights: the desktop app keeps them with its settings, not in the library.
    models = Path(models_dir or os.environ.get("KEYFINDER_MODELS") or data_dir / "models")
    neural.configure(models)
    lyrics.configure(models)
    store = JobStore(data_dir, inline=inline)
    transposer = Transposer(data_dir)
    render_locks: defaultdict[Path, threading.Lock] = defaultdict(threading.Lock)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        store.shutdown()

    app = FastAPI(title="KeyFinder", version=__version__, lifespan=lifespan)
    app.state.store = store

    if token:
        @app.middleware("http")
        async def require_token(request: Request, call_next):
            given = request.headers.get(TOKEN_HEADER, "")
            if not hmac.compare_digest(given.encode(), token.encode()):
                return JSONResponse({"detail": "forbidden"}, status_code=403)
            return await call_next(request)

    def not_found(exc: SongNotFound) -> HTTPException:
        return HTTPException(404, f"not found: {exc.args[0] if exc.args else ''}")

    @app.get("/api/capabilities")
    def capabilities():
        return {
            "version": __version__,
            "api": ENGINE_API,
            "backends": separation.available_backends(),
            "modes": {name: list(stems) for name, stems in separation.MODES.items()},
            "dsp_modes": list(separation.DSP_MODES),
            "rubberband": transform.has_rubberband(),
            "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
            "desktop": bool(token),
            "demucs": neural.status(),
            "lyrics": lyrics.status(),
        }

    @app.post("/api/lyrics/download", status_code=202)
    def download_lyrics_model():
        """Fetch the Whisper model ahead of time (Profile); /api/capabilities shows how it went."""
        if not lyrics.available():
            raise HTTPException(400, "transcription isn't installed in this engine")
        lyrics.download()
        return lyrics.status()

    @app.post("/api/demucs/download", status_code=202)
    def download_demucs(model: str = Body("htdemucs", embed=True)):
        """Fetch a Demucs model ahead of time (Profile); /api/capabilities shows how it went."""
        if not neural.available():
            raise HTTPException(400, "Demucs isn't installed in this engine")
        try:
            neural.download(model)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return neural.status()

    @app.get("/api/songs")
    def list_songs():
        return store.list()

    @app.post("/api/songs", status_code=201)
    def upload(file: UploadFile = File(...), mode: str = Form("4stems"), backend: str = Form("auto"),
               lyrics_mode: str = Form("auto", alias="lyrics", pattern="^(auto|online|off)$")):
        fd, tmp_name = tempfile.mkstemp(dir=data_dir, prefix="upload-")
        tmp = Path(tmp_name)
        try:
            size = 0
            with os.fdopen(fd, "wb") as out:
                while chunk := file.file.read(1 << 20):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise HTTPException(413, f"file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
                    out.write(chunk)
            if size == 0:
                raise HTTPException(400, "empty file")
            song = store.create(file.filename or "Untitled", tmp, mode=mode, backend=backend, lyrics_mode=lyrics_mode)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        finally:
            tmp.unlink(missing_ok=True)
        return store.summary(song)

    @app.post("/api/songs/url", status_code=201)
    def import_url(url: str = Body(...), mode: str = Body("4stems"), backend: str = Body("auto"),
                   lyrics_mode: str = Body("auto", alias="lyrics", pattern="^(auto|online|off)$")):
        fd, tmp_name = tempfile.mkstemp(dir=data_dir, prefix="download-")
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            filename = remote.download(url, tmp, MAX_UPLOAD_BYTES)
            song = store.create(filename, tmp, mode=mode, backend=backend, lyrics_mode=lyrics_mode)
        except ValueError as exc:  # includes remote.UrlImportError
            raise HTTPException(400, str(exc)) from exc
        finally:
            tmp.unlink(missing_ok=True)
        return store.summary(song)

    if token:
        @app.post("/api/songs/local", status_code=201)
        def import_local(paths: list[str] = Body(...), mode: str = Body("4stems"), backend: str = Body("auto"),
                         lyrics_mode: str = Body("auto", alias="lyrics", pattern="^(auto|online|off)$")):
            """Desktop only: import files the user picked in a native dialog or dropped on the window.

            A folder (of stems, or a Player song) or a zip of stems becomes one song with its stems.
            """
            try:
                store.check_options(mode, backend)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            created, failed = [], []
            for raw in paths[:100]:
                source = Path(raw)
                try:
                    if not source.is_absolute():
                        raise ValueError("not a file")
                    if source.is_dir():
                        files = [p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_file()]
                        if not stems.pick_files(files[:5000])["stems"]:
                            raise ValueError("there are no audio files in the folder")
                        created.append(store.summary(store.create(source.name, Path(), package_folder=source,
                                                                  lyrics_mode=lyrics_mode)))
                        continue
                    if not source.is_file():
                        raise ValueError("not a file")
                    limit = MAX_PACKAGE_BYTES if source.suffix.lower() == ".zip" else MAX_UPLOAD_BYTES
                    if source.stat().st_size > limit:
                        raise ValueError(f"larger than {limit // (1024 * 1024)} MB")
                    fd, tmp_name = tempfile.mkstemp(dir=data_dir, prefix="import-")
                    os.close(fd)
                    tmp = Path(tmp_name)
                    try:
                        shutil.copyfile(source, tmp)
                        created.append(store.summary(store.create(source.name, tmp, mode=mode, backend=backend,
                                                                  lyrics_mode=lyrics_mode)))
                    finally:
                        tmp.unlink(missing_ok=True)
                except (OSError, ValueError) as exc:
                    failed.append({"path": raw, "error": str(exc)})
            return {"created": created, "failed": failed}

    @app.patch("/api/songs/{song_id}")
    def edit_song(song_id: str, title: str | None = Body(None), artist: str | None = Body(None),
                  tempo: str | None = Body(None, pattern="^(double|half)$")):
        try:
            if tempo:
                store.scale_tempo(song_id, 2.0 if tempo == "double" else 0.5)
            if title is None and artist is None:
                return store.summary(store.get(song_id))
            return store.summary(store.update_info(song_id, title=title, artist=artist))
        except SongNotFound as exc:
            raise not_found(exc) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/songs/{song_id}/cover")
    def cover(song_id: str):
        try:
            return FileResponse(store.cover_path(song_id), media_type="image/jpeg")
        except SongNotFound as exc:
            raise not_found(exc) from exc

    @app.get("/api/songs/{song_id}")
    def get_song(song_id: str):
        try:
            song = store.get(song_id)
        except SongNotFound as exc:
            raise not_found(exc) from exc
        song.pop("source", None)
        song.pop("package_folder", None)
        song["stem_names"], song["stem_kinds"] = stem_labels(song)
        a = song.get("analysis")
        if a and a.get("beats"):
            # Tempo changes and bar lengths, from the beats as they are now (after a tempo fix too).
            a["beat_map"] = tempo.beat_map(a["beats"], a.get("downbeats") or [], a.get("beats_per_bar", 4))
        return song

    # ------------------------------------------------------------------ transposing files

    def save_upload(file: UploadFile, prefix: str) -> Path:
        fd, tmp_name = tempfile.mkstemp(dir=data_dir, prefix=prefix)
        tmp = Path(tmp_name)
        size = 0
        with os.fdopen(fd, "wb") as out:
            while chunk := file.file.read(1 << 20):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    tmp.unlink(missing_ok=True)
                    raise HTTPException(413, f"file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
                out.write(chunk)
        if size == 0:
            tmp.unlink(missing_ok=True)
            raise HTTPException(400, "empty file")
        return tmp

    @app.post("/api/transpose", status_code=201)
    def transpose_upload(file: UploadFile = File(...)):
        """Add a file to transpose: KeyFinder finds its key and tempo (no stems, not in the library)."""
        tmp = save_upload(file, "transpose-")
        try:
            return transposer.add(file.filename or "Untitled", tmp)
        except (audio.AudioError, ValueError) as exc:
            raise HTTPException(400, f"couldn't read {file.filename}: {exc}") from exc
        finally:
            tmp.unlink(missing_ok=True)

    if token:
        @app.post("/api/transpose/local", status_code=201)
        def transpose_local(paths: list[str] = Body(..., embed=True)):
            """Desktop only: add files to transpose by path."""
            created, failed = [], []
            for raw in paths[:50]:
                source = Path(raw)
                try:
                    if not source.is_absolute() or not source.is_file():
                        raise ValueError("not a file")
                    if source.stat().st_size > MAX_UPLOAD_BYTES:
                        raise ValueError(f"larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
                    fd, tmp_name = tempfile.mkstemp(dir=data_dir, prefix="transpose-")
                    os.close(fd)
                    tmp = Path(tmp_name)
                    try:
                        shutil.copyfile(source, tmp)
                        created.append(transposer.add(source.name, tmp))
                    finally:
                        tmp.unlink(missing_ok=True)
                except (OSError, ValueError, audio.AudioError) as exc:
                    failed.append({"path": raw, "error": str(exc)})
            return {"created": created, "failed": failed}

    @app.get("/api/transpose/{item_id}/render")
    def transpose_render(item_id: str, semitones: int = Query(0, ge=-12, le=12),
                         speed: float = Query(1.0, ge=transform.MIN_SPEED, le=transform.MAX_SPEED),
                         format: str = Query("mp3", pattern="^(" + "|".join(TRANSPOSE_FORMATS) + ")$")):
        """The file in its new key (and speed), as ``format``."""
        try:
            info = transposer.get(item_id)
            dest = transposer.render(item_id, semitones, speed, format)
        except NotFound as exc:
            raise HTTPException(404, "not found") from exc
        except (ValueError, audio.AudioError) as exc:
            raise HTTPException(400, str(exc)) from exc
        k = info["key"]
        parts = [key.key_name((k["tonic"] + semitones) % 12, k["mode"]).replace("#", "♯")]
        if speed != 1.0:
            parts.append(f"{round(speed * 100)}%")
        name = f"{info['name']} ({', '.join(parts)}).{format}"
        return FileResponse(dest, filename=name, background=BackgroundTask(dest.unlink, missing_ok=True))

    @app.delete("/api/transpose/{item_id}", status_code=204)
    def transpose_delete(item_id: str):
        try:
            transposer.delete(item_id)
        except NotFound as exc:
            raise HTTPException(404, "not found") from exc

    @app.post("/api/songs/{song_id}/lyrics", status_code=202)
    def find_lyrics(song_id: str, mode: str | None = Body(None, embed=True, pattern="^(auto|online)$")):
        """Look up / transcribe the lyrics again, or for a song added before there were lyrics."""
        try:
            return store.summary(store.find_lyrics(song_id, mode))
        except SongNotFound as exc:
            raise not_found(exc) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.put("/api/songs/{song_id}/lyrics")
    def edit_lyrics(song_id: str, lines: list[str] = Body(..., embed=True)):
        """Correct the words, line by line (an empty line removes it)."""
        try:
            return store.edit_lyrics(song_id, lines)["lyrics"]
        except SongNotFound as exc:
            raise not_found(exc) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.delete("/api/songs/{song_id}", status_code=204)
    def delete_song(song_id: str):
        try:
            store.delete(song_id)
        except SongNotFound as exc:
            raise not_found(exc) from exc

    @app.get("/api/songs/{song_id}/stems/{stem}")
    def stem_audio(song_id: str, stem: str, semitones: int = Query(0, ge=-12, le=12), download: bool = False):
        try:
            path = store.stem_path(song_id, stem)
            song = store.get(song_id)
        except SongNotFound as exc:
            raise not_found(exc) from exc
        if download:
            name = song["title"] if stem == ORIGINAL else f"{song['title']} ({stem_labels(song)[0].get(stem, stem)})"
            return FileResponse(path, media_type="audio/mpeg", filename=f"{name}.mp3")
        if semitones:
            shifted = path.with_name(f"{stem}.pitch{semitones:+d}.mp3")
            with render_locks[shifted]:
                if not shifted.exists():
                    transform.render(path, shifted, semitones=semitones)
            path = shifted
        return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "max-age=86400"})

    def ready_song(song_id: str) -> tuple[dict, Path]:
        try:
            song = store.get(song_id)
            folder = store.song_dir(song_id)
        except SongNotFound as exc:
            raise not_found(exc) from exc
        if song["status"] != "ready":
            raise HTTPException(409, "song is still processing")
        return song, folder

    @app.get("/api/songs/{song_id}/export/player-name")
    def player_package_name(song_id: str, semitones: int = Query(0, ge=-12, le=12),
                            speed: float = Query(1.0, ge=transform.MIN_SPEED, le=transform.MAX_SPEED)):
        """The name the Player package must keep: Player reads the key and tempo from it."""
        song, _ = ready_song(song_id)
        return {"name": player_export.package_name(song, semitones, speed) + ".zip"}

    @app.get("/api/songs/{song_id}/export")
    def export(
        song_id: str,
        semitones: int = Query(0, ge=-12, le=12),
        speed: float = Query(1.0, ge=transform.MIN_SPEED, le=transform.MAX_SPEED),
        volumes: str = Query("", description="comma-separated stem:volume pairs, e.g. vocals:0,drums:0.5"),
        format: str = Query("mp3", pattern="^(mp3|wav|m4a|player)$"),
    ):
        song, folder = ready_song(song_id)
        exports = folder / "exports"
        exports.mkdir(exist_ok=True)
        if format == "player":
            # Every stem separately, with a click on the song's beats, for Player (volumes don't apply).
            dest = exports / f"player-{os.getpid()}-{threading.get_ident()}.zip"
            player_export.build(song, folder, dest, semitones, speed)
            return FileResponse(dest, media_type="application/zip",
                                filename=player_export.package_name(song, semitones, speed) + ".zip",
                                background=BackgroundTask(dest.unlink, missing_ok=True))
        parts = [s for s in song["stems"] if s != ORIGINAL] or [ORIGINAL]
        levels: dict[str, float] = {}
        for pair in filter(None, volumes.split(",")):
            name, _, value = pair.partition(":")
            if name not in parts:
                raise HTTPException(400, f"unknown stem {name!r}")
            try:
                levels[name] = float(value)
            except ValueError as exc:
                raise HTTPException(400, f"bad volume for {name!r}") from exc
        dest = exports / f"export-{os.getpid()}-{threading.get_ident()}.{format}"
        try:
            transform.mixdown({s: folder / "stems" / f"{s}.mp3" for s in parts}, levels, dest, semitones, speed)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        suffix = []
        if semitones:
            suffix.append(f"{semitones:+d}st")
        if speed != 1.0:
            suffix.append(f"{speed:g}x")
        labels, _ = stem_labels(song)
        muted = [labels.get(s, s) for s in parts if levels.get(s, 1.0) == 0]
        if muted:
            suffix.append("no " + (", ".join(muted) if len(muted) <= 3 else f"{len(muted)} stems"))
        name = song["title"] + (f" ({', '.join(suffix)})" if suffix else "") + f".{format}"
        return FileResponse(dest, filename=name, background=BackgroundTask(dest.unlink, missing_ok=True))

    ui_dir = ui_dir or default_ui_dir()
    if ui_dir:
        app.mount("/", StaticFiles(directory=ui_dir, html=True), name="ui")
    else:
        @app.get("/", response_class=HTMLResponse, include_in_schema=False)
        def no_ui():
            return NO_UI
    return app


def main() -> None:
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="Run the KeyFinder web app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data", default=os.environ.get("KEYFINDER_DATA", "data"), help="where songs are stored")
    args = parser.parse_args()
    Path(args.data).mkdir(parents=True, exist_ok=True)
    uvicorn.run(create_app(args.data), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
