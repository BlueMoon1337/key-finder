"""The desktop app's engine: the API server run as a child process of the Electron app.

The app starts it with::

    keyfinder-engine --data <library folder>      (KEYFINDER_TOKEN in the environment)

It listens on a free port on 127.0.0.1 only, prints one line to stdout once it
is ready::

    KEYFINDER_ENGINE_READY {"port": 51234, "version": "0.2.0"}

and exits when its stdin closes, so it never outlives the app (even if the app
crashes). The token comes through the environment rather than the command
line, where other users' process listings could see it.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import socket
import sys
import threading
from pathlib import Path

READY = "KEYFINDER_ENGINE_READY"


def _exit_with_parent() -> None:
    """Block on stdin; the app holds the other end, so EOF means it has gone."""
    try:
        while sys.stdin.buffer.read(1024):
            pass
    except (OSError, ValueError):
        pass
    os._exit(0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="keyfinder-engine", description=__doc__.split("\n")[0])
    parser.add_argument("--data", required=True, help="library folder where songs are stored")
    parser.add_argument("--models", help="where downloaded Demucs models are kept (default: <data>/models)")
    parser.add_argument("--port", type=int, default=0, help="0 picks a free port")
    parser.add_argument("--no-parent-watch", action="store_true", help="keep running when stdin closes")
    args = parser.parse_args(argv)

    token = os.environ.get("KEYFINDER_TOKEN", "")
    if len(token) < 32:
        print("KEYFINDER_TOKEN must be set to a random string of 32+ characters", file=sys.stderr)
        return 2

    import uvicorn

    from . import ENGINE_API, __version__
    from .server import create_app

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", args.port))
    port = sock.getsockname()[1]

    app = create_app(Path(args.data), token=token, models_dir=Path(args.models) if args.models else None)
    config = uvicorn.Config(app, log_level="warning", access_log=False)
    server = uvicorn.Server(config)

    if not args.no_parent_watch:
        threading.Thread(target=_exit_with_parent, daemon=True, name="parent-watch").start()

    original_startup = server.startup

    async def startup(sockets=None):
        await original_startup(sockets=sockets)
        print(f"{READY} {json.dumps({'port': port, 'version': __version__, 'api': ENGINE_API})}", flush=True)

    server.startup = startup
    server.run(sockets=[sock])
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()  # PyInstaller builds on Windows
    sys.exit(main())
