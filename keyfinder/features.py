"""Spectral features shared by the key, tempo and chord estimators."""

from __future__ import annotations

import numpy as np

HOP = 512
CHROMA_FFT = 8192
ONSET_FFT = 2048
FMIN = 55.0      # A1
FMAX = 4200.0    # roughly C8; overtones above add little to pitch class
# The bass chroma needs finer frequency steps: at E1 (41 Hz) semitones are only 2.4 Hz apart.
BASS_FFT = 16384
BASS_FMIN = 30.0   # B0, the lowest note of a five-string bass
BASS_MAX_MIDI = 52.5  # up to E3


def frame_times(n_frames: int, sr: int, hop: int = HOP) -> np.ndarray:
    return np.arange(n_frames) * hop / sr


def magnitude_spectrogram(y: np.ndarray, n_fft: int, hop: int = HOP, max_bin: int | None = None) -> np.ndarray:
    """|STFT| with a Hann window and centred frames, shape ``(1 + n_fft//2, frames)``.

    ``max_bin`` keeps only the lowest bins, so a long, fine-resolution transform stays small.
    """
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
    bins = n_fft // 2 + 1 if max_bin is None else min(max_bin, n_fft // 2 + 1)
    out = np.empty((bins, n_frames), dtype=np.float32)
    step = 2048 if n_fft <= 8192 else 512
    for start in range(0, n_frames, step):
        out[:, start:start + step] = np.abs(np.fft.rfft(frames[start:start + step] * window, axis=1))[:, :bins].T
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


def bass_chroma(y: np.ndarray, sr: int, tuning: float = 0.0) -> np.ndarray:
    """Pitch classes of the bass register (B0..E3), used to find chord roots and inversions.

    A low bass note's fifth (its third harmonic) can be as loud as its root, so unlike the
    main chroma this keeps magnitudes linear and favours lower frequencies, letting the
    fundamental win. A finer transform resolves the low semitones.
    """
    f_max = 440.0 * 2 ** ((BASS_MAX_MIDI + tuning - 69) / 12)
    max_bin = int(np.ceil(f_max * BASS_FFT / sr)) + 1
    spec = magnitude_spectrogram(y, BASS_FFT, max_bin=max_bin)
    freqs = np.fft.rfftfreq(BASS_FFT, 1.0 / sr)[:max_bin]
    valid = (freqs >= BASS_FMIN) & (freqs <= f_max)
    midi = 69.0 + 12.0 * np.log2(freqs[valid] / 440.0) - tuning
    nearest = np.round(midi)
    weight = np.clip(1.0 - 2.0 * np.abs(midi - nearest), 0.0, 1.0)
    fold = np.zeros((12, int(valid.sum())), dtype=np.float32)
    fold[nearest.astype(int) % 12, np.arange(nearest.size)] = weight
    tilt = (freqs[valid] / BASS_FMIN) ** -1.0  # -6 dB per octave: fundamentals over overtones
    return fold @ (spec[valid] * tilt[:, None].astype(np.float32))


def pitch_features(y: np.ndarray, sr: int, tuning: float | None = None) -> dict:
    """Chroma (rows C, C#, ..., B per frame), bass chroma and the tuning offset.

    Log compression before folding makes the chroma fairly robust to timbre.
    """
    spec = magnitude_spectrogram(y, CHROMA_FFT)
    if tuning is None:
        tuning = estimate_tuning(spec, sr)
    return {
        "chroma": _fold(spec, sr, tuning),
        "bass": bass_chroma(y, sr, tuning),
        "tuning": float(tuning),
    }


def clean_chroma(chroma: np.ndarray, fps: float, pedal_seconds: float = 12.0, pedal_amount: float = 0.6) -> np.ndarray:
    """Chroma for chord recognition, with what isn't the changing harmony turned down.

    * Each frame's median across the 12 pitch classes is its noise floor (drums, breath,
      reverb) and is removed, which sharpens the contrast between chord tones and the rest.
    * A note held for many seconds (a pad or bass pedal on the tonic, common in worship and
      ambient arrangements) is partly removed, so it doesn't outvote the chords above it.
    """
    from scipy import ndimage

    c = np.maximum(0.0, chroma - np.median(chroma, axis=0, keepdims=True))
    window = int(pedal_seconds * fps)
    if c.shape[1] > window:
        steady = ndimage.minimum_filter1d(ndimage.median_filter(c, size=(1, max(1, window // 4))), window, axis=1)
        c = np.maximum(0.0, c - pedal_amount * steady)
    return c


def onset_strength(y: np.ndarray, sr: int, max_freq: float | None = None) -> np.ndarray:
    """Spectral-flux onset envelope at ``sr / HOP`` frames per second, normalised to unit max."""
    spec = magnitude_spectrogram(y, ONSET_FFT)
    if max_freq is not None:
        spec = spec[: int(max_freq * ONSET_FFT / sr) + 1]
    logspec = np.log1p(1000.0 * spec / (spec.max() + 1e-9))
    flux = np.maximum(0.0, np.diff(logspec, axis=1, prepend=logspec[:, :1])).sum(axis=0)
    # Remove the slowly varying loudness trend so quiet and loud sections compare.
    win = max(1, min(flux.size, int(round(0.5 * sr / HOP))))
    trend = np.convolve(flux, np.ones(win) / win, mode="same")
    env = np.maximum(0.0, flux - trend)
    peak = env.max()
    return env / peak if peak > 0 else env
