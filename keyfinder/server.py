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

from . import __version__, remote, separation, transform
from .jobs import ORIGINAL, JobStore, SongNotFound

MAX_UPLOAD_BYTES = int(os.environ.get("KEYFINDER_MAX_UPLOAD_MB", "500")) * 1024 * 1024
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
               ui_dir: Path | None = None) -> FastAPI:
    data_dir = Path(data_dir or os.environ.get("KEYFINDER_DATA", "data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    store = JobStore(data_dir, inline=inline)
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
            "backends": separation.available_backends(),
            "modes": {name: list(stems) for name, stems in separation.MODES.items()},
            "dsp_modes": list(separation.DSP_MODES),
            "rubberband": transform.has_rubberband(),
            "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
            "desktop": bool(token),
        }

    @app.get("/api/songs")
    def list_songs():
        return store.list()

    @app.post("/api/songs", status_code=201)
    def upload(file: UploadFile = File(...), mode: str = Form("4stems"), backend: str = Form("auto")):
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
            song = store.create(file.filename or "Untitled", tmp, mode=mode, backend=backend)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        finally:
            tmp.unlink(missing_ok=True)
        return store.summary(song)

    @app.post("/api/songs/url", status_code=201)
    def import_url(url: str = Body(...), mode: str = Body("4stems"), backend: str = Body("auto")):
        fd, tmp_name = tempfile.mkstemp(dir=data_dir, prefix="download-")
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            filename = remote.download(url, tmp, MAX_UPLOAD_BYTES)
            song = store.create(filename, tmp, mode=mode, backend=backend)
        except ValueError as exc:  # includes remote.UrlImportError
            raise HTTPException(400, str(exc)) from exc
        finally:
            tmp.unlink(missing_ok=True)
        return store.summary(song)

    if token:
        @app.post("/api/songs/local", status_code=201)
        def import_local(paths: list[str] = Body(...), mode: str = Body("4stems"), backend: str = Body("auto")):
            """Desktop only: import files the user picked in a native dialog or dropped on the window."""
            try:
                store.check_options(mode, backend)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            created, failed = [], []
            for raw in paths[:100]:
                source = Path(raw)
                try:
                    if not source.is_absolute() or not source.is_file():
                        raise ValueError("not a file")
                    if source.stat().st_size > MAX_UPLOAD_BYTES:
                        raise ValueError(f"larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
                    fd, tmp_name = tempfile.mkstemp(dir=data_dir, prefix="import-")
                    os.close(fd)
                    tmp = Path(tmp_name)
                    try:
                        shutil.copyfile(source, tmp)
                        created.append(store.summary(store.create(source.name, tmp, mode=mode, backend=backend)))
                    finally:
                        tmp.unlink(missing_ok=True)
                except (OSError, ValueError) as exc:
                    failed.append({"path": raw, "error": str(exc)})
            return {"created": created, "failed": failed}

    @app.patch("/api/songs/{song_id}")
    def edit_song(song_id: str, title: str | None = Body(None), artist: str | None = Body(None)):
        try:
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
        return song

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
            title = store.get(song_id)["title"]
        except SongNotFound as exc:
            raise not_found(exc) from exc
        if download:
            name = title if stem == ORIGINAL else f"{title} ({stem})"
            return FileResponse(path, media_type="audio/mpeg", filename=f"{name}.mp3")
        if semitones:
            shifted = path.with_name(f"{stem}.pitch{semitones:+d}.mp3")
            with render_locks[shifted]:
                if not shifted.exists():
                    transform.render(path, shifted, semitones=semitones)
            path = shifted
        return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "max-age=86400"})

    @app.get("/api/songs/{song_id}/export")
    def export(
        song_id: str,
        semitones: int = Query(0, ge=-12, le=12),
        speed: float = Query(1.0, ge=transform.MIN_SPEED, le=transform.MAX_SPEED),
        volumes: str = Query("", description="comma-separated stem:volume pairs, e.g. vocals:0,drums:0.5"),
        format: str = Query("mp3", pattern="^(mp3|wav|m4a)$"),
    ):
        try:
            song = store.get(song_id)
            folder = store.song_dir(song_id)
        except SongNotFound as exc:
            raise not_found(exc) from exc
        if song["status"] != "ready":
            raise HTTPException(409, "song is still processing")
        stems = [s for s in song["stems"] if s != ORIGINAL] or [ORIGINAL]
        levels: dict[str, float] = {}
        for pair in filter(None, volumes.split(",")):
            name, _, value = pair.partition(":")
            if name not in stems:
                raise HTTPException(400, f"unknown stem {name!r}")
            try:
                levels[name] = float(value)
            except ValueError as exc:
                raise HTTPException(400, f"bad volume for {name!r}") from exc
        exports = folder / "exports"
        exports.mkdir(exist_ok=True)
        dest = exports / f"export-{os.getpid()}-{threading.get_ident()}.{format}"
        try:
            transform.mixdown({s: folder / "stems" / f"{s}.mp3" for s in stems}, levels, dest, semitones, speed)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        suffix = []
        if semitones:
            suffix.append(f"{semitones:+d}st")
        if speed != 1.0:
            suffix.append(f"{speed:g}x")
        muted = [s for s in stems if levels.get(s, 1.0) == 0]
        if muted:
            suffix.append("no " + " ".join(muted))
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
