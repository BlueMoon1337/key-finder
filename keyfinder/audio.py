"""Audio I/O built on the ffmpeg command-line tool.

Decoding and encoding go through ffmpeg so any format it understands
(mp3, m4a, flac, wav, ogg, video files with an audio track, ...) works.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np

ANALYSIS_SR = 22050
SEPARATION_SR = 44100


class AudioError(RuntimeError):
    pass


def ffmpeg_binary() -> str:
    path = shutil.which("ffmpeg")
    if path is None:
        raise AudioError("ffmpeg was not found on PATH; install it to decode audio")
    return path


def load(path: str | Path, sr: int = ANALYSIS_SR, mono: bool = True) -> np.ndarray:
    """Decode ``path`` to float32 samples in [-1, 1].

    Returns shape ``(n,)`` when ``mono`` else ``(2, n)``.
    """
    channels = 1 if mono else 2
    cmd = [
        ffmpeg_binary(), "-v", "error", "-nostdin", "-i", str(path),
        "-vn", "-f", "f32le", "-ac", str(channels), "-ar", str(sr), "-",
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise AudioError(f"could not decode {path}: {proc.stderr.decode(errors='replace').strip()}")
    y = np.frombuffer(proc.stdout, dtype=np.float32)
    if y.size == 0:
        raise AudioError(f"{path} contains no audio")
    if mono:
        return y.copy()
    return y.reshape(-1, 2).T.copy()


def save(path: str | Path, y: np.ndarray, sr: int, bitrate: str = "192k") -> None:
    """Encode samples to ``path``; the container/codec follows the extension."""
    y = np.atleast_2d(np.asarray(y, dtype=np.float32))
    channels = y.shape[0]
    cmd = [
        ffmpeg_binary(), "-v", "error", "-nostdin", "-y",
        "-f", "f32le", "-ac", str(channels), "-ar", str(sr), "-i", "-",
    ]
    if Path(path).suffix.lower() in (".mp3", ".m4a", ".ogg"):
        cmd += ["-b:a", bitrate]
    cmd.append(str(path))
    data = np.clip(y, -1.0, 1.0).T.astype(np.float32).tobytes()
    proc = subprocess.run(cmd, input=data, capture_output=True)
    if proc.returncode != 0:
        raise AudioError(f"could not encode {path}: {proc.stderr.decode(errors='replace').strip()}")


def has_filter(name: str) -> bool:
    proc = subprocess.run([ffmpeg_binary(), "-hide_banner", "-filters"], capture_output=True, text=True)
    return any(line.split()[1:2] == [name] for line in proc.stdout.splitlines() if line.strip())


def waveform_peaks(y: np.ndarray, points: int = 1200) -> list[float]:
    """Downsampled peak envelope for drawing a waveform overview."""
    y = np.abs(np.asarray(y))
    if y.ndim > 1:
        y = y.max(axis=0)
    if y.size == 0:
        return []
    points = min(points, y.size)
    edges = np.linspace(0, y.size, points + 1).astype(int)
    peaks = np.maximum.reduceat(y, edges[:-1])
    top = peaks.max() or 1.0
    return [round(float(p), 4) for p in peaks / top]
