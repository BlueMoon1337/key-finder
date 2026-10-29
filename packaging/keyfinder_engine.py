"""PyInstaller entry point for the desktop engine (see keyfinder/engine.py)."""

import multiprocessing
import sys

from keyfinder.engine import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
