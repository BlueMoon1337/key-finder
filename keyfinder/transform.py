"""Offline pitch shifting and mixdown rendering.

Speed changes happen live in the player (``playbackRate`` with pitch
preservation), but a browser engine cannot shift pitch independently of
speed, so transposed stems are rendered here and cached next to the originals.

Pitch and tempo use FFmpeg's ``asetrate``/``atempo`` filters through PyAV.
When a system ``ffmpeg`` with the higher-quality, formant-preserving
``rubberband`` filter is on the PATH, it is used instead.
"""

from __future__ import annotations

import functools
import shutil
import subprocess
from pathlib import Path

import numpy as np

from . import audio

MAX_SEMITONES = 12
MIN_SPEED, MAX_SPEED = 0.25, 3.0
SR = audio.SEPARATION_SR


@functools.lru_cache(maxsize=1)
def rubberband_ffmpeg() -> str | None:
    """Path of a system ffmpeg that has the rubberband filter, if there is one."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    try:
        proc = subprocess.run([ffmpeg, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    has = any(line.split()[1:2] == ["rubberband"] for line in proc.stdout.splitlines() if line.strip())
    return ffmpeg if has else None


def has_rubberband() -> bool:
    return rubberband_ffmpeg() is not None


def _atempo_chain(factor: float) -> list[tuple[str, str]]:
    """``atempo`` accepts 0.5..2.0 per instance, so chain several for larger factors."""
    parts = []
    while factor > 2.0:
        parts.append(("atempo", "2.0"))
        factor /= 2.0
    while factor < 0.5:
        parts.append(("atempo", "0.5"))
        factor /= 0.5
    parts.append(("atempo", f"{factor:.6f}"))
    return parts


def _check(semitones: float, speed: float) -> None:
    if not -MAX_SEMITONES <= semitones <= MAX_SEMITONES:
        raise ValueError(f"semitones must be within ±{MAX_SEMITONES}")
    if not MIN_SPEED <= speed <= MAX_SPEED:
        raise ValueError(f"speed must be within {MIN_SPEED}..{MAX_SPEED}")


def pitch_tempo_filters(semitones: float, speed: float = 1.0, sr: int = SR) -> list[tuple[str, str]]:
    """FFmpeg filters that shift pitch by ``semitones`` and tempo by ``speed``."""
    _check(semitones, speed)
    if semitones == 0 and speed == 1.0:
        return []
    if semitones == 0:
        return _atempo_chain(speed)
    # Resampling moves the pitch but also the tempo; atempo puts the tempo back.
    ratio = 2.0 ** (semitones / 12.0)
    return [("asetrate", f"{sr * ratio:.3f}"), ("aresample", str(sr)), *_atempo_chain(speed / ratio)]


def shift(y: np.ndarray, semitones: float = 0.0, speed: float = 1.0, sr: int = SR) -> np.ndarray:
    _check(semitones, speed)
    if semitones == 0 and speed == 1.0:
        return np.atleast_2d(y)
    ffmpeg = rubberband_ffmpeg()
    if ffmpeg:
        return _rubberband(ffmpeg, np.atleast_2d(y), semitones, speed, sr)
    return audio.apply_filters(y, sr, pitch_tempo_filters(semitones, speed, sr))


def _rubberband(ffmpeg: str, y: np.ndarray, semitones: float, speed: float, sr: int) -> np.ndarray:
    channels = y.shape[0]
    flt = f"rubberband=pitch={2.0 ** (semitones / 12.0):.6f}:tempo={speed:.6f}:pitchq=quality:formant=preserved"
    cmd = [ffmpeg, "-v", "error", "-nostdin", "-f", "f32le", "-ac", str(channels), "-ar", str(sr), "-i", "-",
           "-af", flt, "-f", "f32le", "-ac", str(channels), "-ar", str(sr), "-"]
    proc = subprocess.run(cmd, input=np.ascontiguousarray(y.T, dtype=np.float32).tobytes(), capture_output=True)
    if proc.returncode != 0:
        raise audio.AudioError(proc.stderr.decode(errors="replace").strip())
    return np.frombuffer(proc.stdout, dtype=np.float32).reshape(-1, channels).T.copy()


def render(source: Path, dest: Path, semitones: float = 0.0, speed: float = 1.0) -> Path:
    """Write a pitch/tempo-shifted copy of ``source`` to ``dest``."""
    _check(semitones, speed)
    y = shift(audio.load(source, SR, mono=False), semitones, speed)
    _save_atomic(dest, y)
    return dest


def mixdown(sources: dict[str, Path], volumes: dict[str, float], dest: Path,
            semitones: float = 0.0, speed: float = 1.0) -> Path:
    """Mix stems at the given volumes (0..2), apply pitch/tempo and encode to ``dest``."""
    _check(semitones, speed)
    names = [n for n in sources if volumes.get(n, 1.0) > 0]
    if not names:
        raise ValueError("every stem is muted; nothing to export")
    mix = None
    for name in names:
        stem = audio.load(sources[name], SR, mono=False) * float(np.clip(volumes.get(name, 1.0), 0.0, 2.0))
        if mix is None:
            mix = stem
        else:
            n = max(mix.shape[1], stem.shape[1])
            mix = np.pad(mix, ((0, 0), (0, n - mix.shape[1]))) + np.pad(stem, ((0, 0), (0, n - stem.shape[1])))
    mix = shift(mix, semitones, speed)
    peak = float(np.abs(mix).max()) if mix.size else 0.0
    if peak > 0.98:
        mix *= 0.98 / peak  # boosted stems can clip; scale the whole mix rather than distort it
    _save_atomic(dest, mix)
    return dest


def _save_atomic(dest: Path, y: np.ndarray) -> None:
    tmp = dest.with_name(dest.stem + ".partial" + dest.suffix)
    try:
        audio.save(tmp, y, SR)
        tmp.replace(dest)  # concurrent requests never see a half-written file
    finally:
        tmp.unlink(missing_ok=True)
