"""Stem separation.

Two backends:

* ``demucs`` - Meta's Hybrid Transformer Demucs, a neural model with
  state-of-the-art quality (see neural.py). Used automatically when the
  ``demucs`` package is installed: it's bundled in the desktop app, and
  ``pip install -e .[ml]`` adds it to a source checkout.
* ``dsp`` - a dependency-free fallback using harmonic/percussive median
  filtering, stereo centre extraction and frequency crossovers. It is fast
  and always available but much rougher; it is meant for practice use
  (e.g. turning the drums down) rather than clean isolation.

Both return stems whose sum reconstructs the input mix.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
from scipy import ndimage, signal

from . import audio, neural

Progress = Callable[[float], None]

MODES = {
    "2stems": ("vocals", "accompaniment"),
    "4stems": ("vocals", "drums", "bass", "other"),
    "6stems": ("vocals", "drums", "bass", "guitar", "piano", "other"),
}
DSP_MODES = ("2stems", "4stems")


def demucs_available() -> bool:
    return neural.available()


def available_backends() -> list[str]:
    return (["demucs"] if demucs_available() else []) + ["dsp"]


def choose_backend(requested: str = "auto", mode: str = "4stems") -> str:
    if requested == "auto":
        return "demucs" if demucs_available() else "dsp"
    if requested == "demucs" and not demucs_available():
        raise ValueError("the demucs backend is not installed (pip install -e .[ml])")
    if requested == "dsp" and mode not in DSP_MODES:
        raise ValueError(f"the dsp backend supports {', '.join(DSP_MODES)} only")
    if requested not in ("demucs", "dsp"):
        raise ValueError(f"unknown backend {requested!r}")
    return requested


def separate(
    path: str | Path,
    mode: str = "4stems",
    backend: str = "auto",
    progress: Progress | None = None,
    should_stop: Callable[[], bool] | None = None,
    on_download: Callable[[], None] | None = None,
) -> tuple[dict[str, np.ndarray], int]:
    """Split the file at ``path`` into stereo stems ``{name: (2, n)}``; returns (stems, sample_rate).

    ``progress`` gets 0..1 as the work goes; ``should_stop`` is asked now and then and
    cancels the separation (raising :class:`neural.Cancelled`) when it answers True.
    ``on_download`` is called before the Demucs model is downloaded the first time.
    """
    if mode not in MODES:
        raise ValueError(f"unknown separation mode {mode!r}; choose from {', '.join(MODES)}")
    backend = choose_backend(backend, mode)
    y = audio.load(path, audio.SEPARATION_SR, mono=False)
    if backend == "demucs":
        return neural.separate(y, mode, progress, should_stop, on_download), audio.SEPARATION_SR
    if mode not in DSP_MODES:
        mode = "4stems"
    return separate_dsp(y, audio.SEPARATION_SR, mode, progress, should_stop), audio.SEPARATION_SR


# --------------------------------------------------------------------------- dsp

N_FFT = 4096
HOP = 1024
BLOCK_SECONDS = 30.0
PAD_SECONDS = 2.0


def _soft_mask(target: np.ndarray, other: np.ndarray, power: float = 2.0) -> np.ndarray:
    t, o = target ** power, other ** power
    return t / np.maximum(t + o, 1e-12)


def _masks(spec_l: np.ndarray, spec_r: np.ndarray, sr: int, mode: str) -> dict[str, np.ndarray]:
    """Time-frequency masks that sum to one in every bin."""
    mag = 0.5 * (np.abs(spec_l) + np.abs(spec_r))
    # Fitzgerald HPSS: sustained notes are smooth along time, hits along frequency.
    harmonic = ndimage.median_filter(mag, size=(1, 17))
    percussive = ndimage.median_filter(mag, size=(17, 1))
    perc_mask = _soft_mask(percussive, harmonic)

    freqs = np.fft.rfftfreq(N_FFT, 1.0 / sr)[:, None]
    # Centre-panned energy: left and right nearly identical in level and phase.
    cross = np.abs(spec_l * np.conj(spec_r))
    power = np.abs(spec_l) ** 2 + np.abs(spec_r) ** 2
    similarity = np.real(spec_l * np.conj(spec_r)) / np.maximum(0.5 * power, 1e-12)
    centre = np.clip(similarity, 0.0, 1.0) * (2 * cross / np.maximum(power, 1e-12))
    centre = ndimage.uniform_filter(centre, size=(3, 5)) ** 4
    # Most lead-vocal energy lies between ~120 Hz and ~7 kHz.
    vocal_band = 1.0 / (1.0 + (120.0 / np.maximum(freqs, 1.0)) ** 4) / (1.0 + (freqs / 7000.0) ** 4)

    harm_mask = 1.0 - perc_mask
    vocals = harm_mask * centre * vocal_band
    if mode == "2stems":
        return {"vocals": vocals, "accompaniment": 1.0 - vocals}

    low = 1.0 / (1.0 + (freqs / 180.0) ** 6)  # crossover for the bass stem
    drums = perc_mask * (1.0 - 0.5 * low)      # kick fundamentals share the bass band
    bass = (1.0 - drums) * low
    vocals = vocals * (1.0 - low)
    other = np.clip(1.0 - drums - bass - vocals, 0.0, 1.0)
    return {"vocals": vocals, "drums": drums, "bass": bass, "other": other}


def _separate_block(y: np.ndarray, sr: int, mode: str) -> dict[str, np.ndarray]:
    if y.shape[0] == 1:
        y = np.vstack([y, y])
    _, _, spec = signal.stft(y, sr, nperseg=N_FFT, noverlap=N_FFT - HOP)
    masks = _masks(spec[0], spec[1], sr, mode)
    stems = {}
    for name, mask in masks.items():
        _, out = signal.istft(spec * mask[None], sr, nperseg=N_FFT, noverlap=N_FFT - HOP)
        stems[name] = out[:, : y.shape[1]].astype(np.float32)
    return stems


def separate_dsp(y: np.ndarray, sr: int, mode: str = "4stems", progress: Progress | None = None,
                 should_stop: Callable[[], bool] | None = None) -> dict[str, np.ndarray]:
    """Separate a ``(channels, n)`` signal in overlapping blocks to bound memory use."""
    y = np.atleast_2d(np.asarray(y, dtype=np.float32))
    n = y.shape[1]
    block = int(BLOCK_SECONDS * sr)
    pad = int(PAD_SECONDS * sr)
    names = MODES[mode]
    out = {name: np.zeros((2, n), dtype=np.float32) for name in names}
    for start in range(0, n, block):
        lo, hi = max(0, start - pad), min(n, start + block + pad)
        stems = _separate_block(y[:, lo:hi], sr, mode)
        keep = slice(start - lo, start - lo + min(block, n - start))
        for name in names:
            out[name][:, start:start + min(block, n - start)] = stems[name][:, keep]
        if progress:
            progress(min(1.0, (start + block) / n))
        if should_stop and should_stop():
            raise neural.Cancelled()
    return out
