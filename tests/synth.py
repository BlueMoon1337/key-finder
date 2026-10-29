"""Synthetic test signals: chord progressions with a bass line and a drum click."""

from __future__ import annotations

import numpy as np

SR = 22050


def tone(midi: float, seconds: float, sr: int = SR, harmonics: int = 5) -> np.ndarray:
    t = np.arange(int(seconds * sr)) / sr
    f = 440.0 * 2 ** ((midi - 69) / 12)
    y = sum((0.6 ** h) * np.sin(2 * np.pi * f * (h + 1) * t) for h in range(harmonics))
    env = np.minimum(1.0, t / 0.01) * np.exp(-1.5 * t)
    return (y * env).astype(np.float32)


def click(sr: int = SR) -> np.ndarray:
    n = int(0.03 * sr)
    rng = np.random.default_rng(0)
    return (rng.standard_normal(n) * np.exp(-np.arange(n) / (0.005 * sr))).astype(np.float32)


CHORD_INTERVALS = {"maj": (0, 4, 7), "min": (0, 3, 7), "7": (0, 4, 7, 10)}


def progression(chords: list[tuple[int, str]], bpm: float = 120.0, beats_per_chord: int = 4,
                repeats: int = 2, sr: int = SR, drums: bool = True) -> np.ndarray:
    """Render ``[(root_pitch_class, quality), ...]`` with a piano-like pad, bass and clicks."""
    beat = 60.0 / bpm
    total = len(chords) * beats_per_chord * repeats
    y = np.zeros(int((total + 1) * beat * sr), dtype=np.float32)
    k = click(sr)
    for b in range(total):
        root, quality = chords[(b // beats_per_chord) % len(chords)]
        start = int(b * beat * sr)
        note = np.zeros(int(beat * sr), dtype=np.float32)
        for interval in CHORD_INTERVALS[quality]:
            note += 0.25 * tone(60 + root + interval, beat, sr)
        note += 0.35 * tone(36 + root, beat, sr, harmonics=3)
        y[start:start + note.size] += note
        if drums:
            y[start:start + k.size] += (0.8 if b % 4 == 0 else 0.5) * k
    return y / np.abs(y).max()
