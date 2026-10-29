"""Offline pitch shifting and mixdown rendering with ffmpeg.

Speed changes happen live in the browser (``playbackRate`` with pitch
preservation), but browsers cannot shift pitch independently of speed, so
transposed stems are rendered here and cached next to the originals.
"""

from __future__ import annotations

import functools
import subprocess
from pathlib import Path

from . import audio

MAX_SEMITONES = 12
MIN_SPEED, MAX_SPEED = 0.25, 3.0


@functools.lru_cache(maxsize=1)
def has_rubberband() -> bool:
    return audio.has_filter("rubberband")


def _atempo_chain(factor: float) -> list[str]:
    """``atempo`` accepts 0.5..2.0 per instance, so chain several for larger factors."""
    parts = []
    while factor > 2.0:
        parts.append("atempo=2.0")
        factor /= 2.0
    while factor < 0.5:
        parts.append("atempo=0.5")
        factor /= 0.5
    parts.append(f"atempo={factor:.6f}")
    return parts


def pitch_tempo_filter(semitones: float, speed: float = 1.0, sr: int = audio.SEPARATION_SR) -> str | None:
    """An ffmpeg audio filter that shifts pitch by ``semitones`` and tempo by ``speed``."""
    if not -MAX_SEMITONES <= semitones <= MAX_SEMITONES:
        raise ValueError(f"semitones must be within ±{MAX_SEMITONES}")
    if not MIN_SPEED <= speed <= MAX_SPEED:
        raise ValueError(f"speed must be within {MIN_SPEED}..{MAX_SPEED}")
    if semitones == 0 and speed == 1.0:
        return None
    ratio = 2.0 ** (semitones / 12.0)
    if has_rubberband():
        return f"rubberband=pitch={ratio:.6f}:tempo={speed:.6f}:pitchq=quality:formant=preserved"
    # Fallback: resample to move pitch (which also changes tempo), then undo
    # the tempo change with atempo.
    chain = [f"asetrate={sr * ratio:.3f}", f"aresample={sr}"]
    return ",".join(chain + _atempo_chain(speed / ratio))


def render(source: Path, dest: Path, semitones: float = 0.0, speed: float = 1.0) -> Path:
    """Write a pitch/tempo-shifted copy of ``source`` to ``dest``."""
    flt = pitch_tempo_filter(semitones, speed)
    cmd = [audio.ffmpeg_binary(), "-v", "error", "-nostdin", "-y", "-i", str(source)]
    if flt:
        cmd += ["-af", flt]
    cmd += ["-ar", str(audio.SEPARATION_SR), "-b:a", "192k", str(dest)]
    _run(cmd, dest)
    return dest


def mixdown(sources: dict[str, Path], volumes: dict[str, float], dest: Path,
            semitones: float = 0.0, speed: float = 1.0) -> Path:
    """Mix stems at the given volumes (0..1), apply pitch/tempo and encode to ``dest``."""
    names = [n for n in sources if volumes.get(n, 1.0) > 0]
    if not names:
        raise ValueError("every stem is muted; nothing to export")
    cmd = [audio.ffmpeg_binary(), "-v", "error", "-nostdin", "-y"]
    for name in names:
        cmd += ["-i", str(sources[name])]
    graph = [f"[{i}:a]volume={max(0.0, min(volumes.get(n, 1.0), 2.0)):.4f}[s{i}]" for i, n in enumerate(names)]
    inputs = "".join(f"[s{i}]" for i in range(len(names)))
    # normalize=0 keeps the stems' relative levels so the sum equals the mix.
    mix = f"{inputs}amix=inputs={len(names)}:normalize=0:dropout_transition=0"
    flt = pitch_tempo_filter(semitones, speed)
    graph.append(mix + (f",{flt}" if flt else "") + ",alimiter=limit=0.98[out]")
    cmd += ["-filter_complex", ";".join(graph), "-map", "[out]", "-ar", str(audio.SEPARATION_SR)]
    if dest.suffix.lower() in (".mp3", ".m4a"):
        cmd += ["-b:a", "256k"]
    cmd.append(str(dest))
    _run(cmd, dest)
    return dest


def _run(cmd: list[str], dest: Path) -> None:
    tmp = dest.with_name(dest.stem + ".partial" + dest.suffix)
    cmd = cmd[:-1] + [str(tmp)]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise audio.AudioError(proc.stderr.decode(errors="replace").strip())
    tmp.replace(dest)  # atomic, so concurrent requests never see a half-written file
