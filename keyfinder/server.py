"""HTTP API and static web app."""

from __future__ import annotations

import os
import tempfile
import threading
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from . import __version__, separation, transform
from .jobs import ORIGINAL, JobStore, SongNotFound

STATIC = Path(__file__).parent / "static"
MAX_UPLOAD_BYTES = int(os.environ.get("KEYFINDER_MAX_UPLOAD_MB", "200")) * 1024 * 1024


def create_app(data_dir: str | Path | None = None, inline: bool = False) -> FastAPI:
    data_dir = Path(data_dir or os.environ.get("KEYFINDER_DATA", "data"))
    store = JobStore(data_dir, inline=inline)
    render_locks: defaultdict[Path, threading.Lock] = defaultdict(threading.Lock)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        store.shutdown()

    app = FastAPI(title="KeyFinder", version=__version__, lifespan=lifespan)
    app.state.store = store

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
    def stem_audio(song_id: str, stem: str, semitones: int = Query(0, ge=-12, le=12)):
        try:
            path = store.stem_path(song_id, stem)
        except SongNotFound as exc:
            raise not_found(exc) from exc
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

    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
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
