"""Spectral features shared by the key, tempo and chord estimators."""

from __future__ import annotations

import numpy as np

HOP = 512
CHROMA_FFT = 8192
ONSET_FFT = 2048
FMIN = 55.0      # A1
FMAX = 4200.0    # roughly C8; overtones above add little to pitch class


def frame_times(n_frames: int, sr: int, hop: int = HOP) -> np.ndarray:
    return np.arange(n_frames) * hop / sr


def magnitude_spectrogram(y: np.ndarray, n_fft: int, hop: int = HOP) -> np.ndarray:
    """|STFT| with a Hann window and centred frames, shape ``(1 + n_fft//2, frames)``."""
    y = np.asarray(y, dtype=np.float32)
    y = np.pad(y, n_fft // 2)
    if y.size < n_fft:
        y = np.pad(y, (0, n_fft - y.size))
    n_frames = 1 + (y.size - n_fft) // hop
    frames = np.lib.stride_tricks.as_strided(
        y, shape=(n_frames, n_fft), strides=(y.strides[0] * hop, y.strides[0]), writeable=False
    )
    window = np.hanning(n_fft).astype(np.float32)
    # Chunk the FFT so long tracks do not allocate one giant complex array.
    out = np.empty((n_fft // 2 + 1, n_frames), dtype=np.float32)
    step = 2048
    for start in range(0, n_frames, step):
        out[:, start:start + step] = np.abs(np.fft.rfft(frames[start:start + step] * window, axis=1)).T
    return out


def _bin_midi(sr: int, n_fft: int) -> tuple[np.ndarray, np.ndarray]:
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    valid = (freqs >= FMIN) & (freqs <= FMAX)
    midi = np.full(freqs.shape, np.nan)
    midi[valid] = 69.0 + 12.0 * np.log2(freqs[valid] / 440.0)
    return freqs, midi


def estimate_tuning(spec: np.ndarray, sr: int, n_fft: int = CHROMA_FFT) -> float:
    """Deviation from A440 in semitones (-0.5..0.5), from spectral peak positions."""
    _, midi = _bin_midi(sr, n_fft)
    mean_spec = spec.mean(axis=1)
    peaks = (mean_spec[1:-1] > mean_spec[:-2]) & (mean_spec[1:-1] > mean_spec[2:])
    idx = np.flatnonzero(peaks) + 1
    idx = idx[~np.isnan(midi[idx])]
    if idx.size == 0:
        return 0.0
    # Refine each peak with parabolic interpolation before reading its pitch.
    a, b, c = np.log(mean_spec[idx - 1] + 1e-9), np.log(mean_spec[idx] + 1e-9), np.log(mean_spec[idx + 1] + 1e-9)
    denom = a - 2 * b + c
    shift = np.where(np.abs(denom) > 1e-12, 0.5 * (a - c) / np.where(denom == 0, 1, denom), 0.0)
    freqs = (idx + np.clip(shift, -0.5, 0.5)) * sr / n_fft
    peak_midi = 69.0 + 12.0 * np.log2(freqs / 440.0)
    weights = mean_spec[idx]
    angle = 2 * np.pi * peak_midi
    mean_angle = np.arctan2(np.sum(weights * np.sin(angle)), np.sum(weights * np.cos(angle)))
    return float(mean_angle / (2 * np.pi))


def _fold(spec: np.ndarray, sr: int, tuning: float, max_midi: float | None = None) -> np.ndarray:
    """Fold FFT bins onto 12 pitch classes with a triangular weight per semitone."""
    _, midi = _bin_midi(sr, CHROMA_FFT)
    valid = ~np.isnan(midi)
    if max_midi is not None:
        valid &= midi <= max_midi
    midi_v = midi[valid] - tuning
    nearest = np.round(midi_v)
    weight = np.clip(1.0 - 2.0 * np.abs(midi_v - nearest), 0.0, 1.0)
    pitch_class = nearest.astype(int) % 12
    fold = np.zeros((12, int(valid.sum())), dtype=np.float32)
    fold[pitch_class, np.arange(pitch_class.size)] = weight
    return fold @ np.log1p(10.0 * spec[valid] / (spec.max() + 1e-9))


def pitch_features(y: np.ndarray, sr: int, tuning: float | None = None) -> dict:
    """Chroma (rows C, C#, ..., B per frame), bass chroma and the tuning offset.

    Log compression before folding makes the profile fairly robust to timbre.
    The bass chroma covers only A1..E3 and is used to find chord roots.
    """
    spec = magnitude_spectrogram(y, CHROMA_FFT)
    if tuning is None:
        tuning = estimate_tuning(spec, sr)
    return {
        "chroma": _fold(spec, sr, tuning),
        "bass": _fold(spec, sr, tuning, max_midi=52.5 + tuning),
        "tuning": float(tuning),
    }


def onset_strength(y: np.ndarray, sr: int, max_freq: float | None = None) -> np.ndarray:
    """Spectral-flux onset envelope at ``sr / HOP`` frames per second, normalised to unit max."""
    spec = magnitude_spectrogram(y, ONSET_FFT)
    if max_freq is not None:
        spec = spec[: int(max_freq * ONSET_FFT / sr) + 1]
    logspec = np.log1p(1000.0 * spec / (spec.max() + 1e-9))
    flux = np.maximum(0.0, np.diff(logspec, axis=1, prepend=logspec[:, :1])).sum(axis=0)
    # Remove the slowly varying loudness trend so quiet and loud sections compare.
    win = max(1, int(round(0.5 * sr / HOP)))
    trend = np.convolve(flux, np.ones(win) / win, mode="same")
    env = np.maximum(0.0, flux - trend)
    peak = env.max()
    return env / peak if peak > 0 else env
