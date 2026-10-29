"""Command-line interface: ``keyfinder analyze|separate|serve``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import analysis, audio, separation


def _fmt_time(seconds: float) -> str:
    return f"{int(seconds // 60)}:{seconds % 60:04.1f}"


def cmd_analyze(args: argparse.Namespace) -> int:
    for path in args.files:
        result = analysis.analyze_file(path)
        if args.json:
            result.pop("waveform", None)
            print(json.dumps({"file": path, **result}, indent=2))
            continue
        k = result["key"]
        print(f"{path}")
        print(f"  Key:    {k['name']} ({k['camelot']}), confidence {k['confidence']:.0%}; relative {k['relative']}")
        print(f"  Tempo:  {result['bpm']} BPM, {len(result['beats'])} beats")
        print(f"  Tuning: {result['tuning_cents']:+.0f} cents from A440")
        if args.chords:
            print(f"  Chords ({args.level}):")
            for seg in result["chords"][args.level]:
                print(f"    {_fmt_time(seg['start']):>7}  {seg['label']}")
    return 0


def cmd_separate(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stems, sr = separation.separate(args.file, args.mode, args.backend)
    for name, data in stems.items():
        dest = out / f"{Path(args.file).stem} - {name}.{args.format}"
        audio.save(dest, data, sr)
        print(dest)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="keyfinder", description="Key, tempo and chord detection plus stem separation"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("analyze", help="detect key, tempo and chords")
    p.add_argument("files", nargs="+")
    p.add_argument("--chords", action="store_true", help="print the chord timeline")
    p.add_argument("--level", choices=["basic", "intermediate", "advanced"], default="intermediate")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("separate", help="split a song into stems")
    p.add_argument("file")
    p.add_argument("--mode", choices=list(separation.MODES), default="4stems")
    p.add_argument("--backend", choices=["auto", "demucs", "dsp"], default="auto")
    p.add_argument("--out", default="stems")
    p.add_argument("--format", choices=["wav", "mp3", "flac"], default="wav")
    p.set_defaults(func=cmd_separate)

    p = sub.add_parser("serve", help="run the web app")
    p.set_defaults(func=None)

    args, rest = parser.parse_known_args(argv)
    if args.command == "serve":
        from .server import main as serve
        sys.argv = ["keyfinder serve", *rest]
        serve()
        return 0
    try:
        return args.func(args)
    except (audio.AudioError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
