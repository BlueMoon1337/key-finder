"""Tempo estimation and beat tracking (Ellis 2007 dynamic-programming tracker)."""

from __future__ import annotations

import numpy as np

MIN_BPM = 50.0
MAX_BPM = 220.0
PRIOR_BPM = 120.0   # centre of the log-normal tempo prior
PRIOR_OCTAVES = 1.0  # its spread, in octaves


def tempo_strength(onset: np.ndarray, fps: float) -> tuple[np.ndarray, np.ndarray]:
    """Prior-weighted autocorrelation on a 0.25 BPM grid; returns (bpms, strength)."""
    # Light smoothing keeps a peak from splitting across two integer lags.
    kernel = np.exp(-0.5 * np.arange(-3, 4) ** 2)
    env = np.convolve(onset, kernel / kernel.sum(), mode="same")
    env = env - env.mean()
    n = env.size
    spectrum = np.fft.rfft(env, 2 * n)
    ac = np.fft.irfft(spectrum * np.conj(spectrum))[:n]
    ac /= np.arange(n, 0, -1)  # unbiased: later lags overlap fewer frames
    bpms = np.arange(MIN_BPM, MAX_BPM + 0.25, 0.25)
    lags = 60.0 * fps / bpms
    frames = np.arange(n)
    beat = np.interp(lags, frames, ac, right=0.0)
    # A true beat period also correlates at twice and half its length; an
    # eighth-note or half-time pulse matches only one of those.
    double = np.interp(2 * lags, frames, ac, right=0.0)
    half = np.interp(lags / 2, frames, ac, right=0.0)
    strength = np.maximum(beat, 0) + 0.5 * np.maximum(double, 0) + 0.25 * np.maximum(half, 0)
    prior = np.exp(-0.5 * (np.log2(bpms / PRIOR_BPM) / PRIOR_OCTAVES) ** 2)
    return bpms, strength * prior


def estimate_tempo(onset: np.ndarray, fps: float) -> float:
    if onset.size < 4:
        return PRIOR_BPM
    bpms, strength = tempo_strength(onset, fps)
    if strength.max() <= 0:
        return PRIOR_BPM
    return float(bpms[int(np.argmax(strength))])


def track_beats(onset: np.ndarray, fps: float, bpm: float, tightness: float = 100.0) -> np.ndarray:
    """Beat frame indices that best line up with onsets at roughly ``bpm``."""
    n = onset.size
    if n == 0 or onset.max() <= 0:
        return np.zeros(0, dtype=int)
    period = 60.0 * fps / bpm
    width = max(1, int(round(period / 16)))
    kernel = np.exp(-0.5 * (np.arange(-2 * width, 2 * width + 1) / width) ** 2)
    local = np.convolve(onset / (onset.std() + 1e-9), kernel, mode="same")

    window = np.arange(-int(round(2 * period)), -int(round(period / 2)) + 1)
    penalty = -tightness * np.log(-window / period) ** 2
    cumulative = np.zeros(n)
    backlink = np.full(n, -1, dtype=int)
    for t in range(n):
        candidates = t + window
        ok = candidates >= 0
        if ok.any():
            scores = cumulative[candidates[ok]] + penalty[ok]
            best = int(np.argmax(scores))
            if scores[best] > 0:
                cumulative[t] = local[t] + scores[best]
                backlink[t] = candidates[ok][best]
                continue
        cumulative[t] = local[t]

    # Start the backtrace from the last strong local maximum of the cumulative score.
    maxima = np.flatnonzero((cumulative[1:-1] >= cumulative[:-2]) & (cumulative[1:-1] >= cumulative[2:])) + 1
    if maxima.size == 0:
        return np.zeros(0, dtype=int)
    threshold = 0.5 * np.median(cumulative[maxima])
    end = int(maxima[cumulative[maxima] >= threshold][-1])
    beats = [end]
    while backlink[beats[-1]] >= 0:
        beats.append(int(backlink[beats[-1]]))
    beats = np.array(beats[::-1])

    # Trim weak beats at the edges (fade-in/out, silence).
    strength = local[beats]
    keep = strength > 0.1 * np.median(strength) if strength.size else np.zeros(0, bool)
    if keep.any():
        first, last = np.flatnonzero(keep)[[0, -1]]
        beats = beats[first:last + 1]
    return beats


def estimate_downbeat_phase(bass_onset: np.ndarray, beats: np.ndarray, beats_per_bar: int = 4) -> int:
    """Index of the first downbeat among ``beats``, guessed from low-frequency accents."""
    if beats.size < beats_per_bar:
        return 0
    accents = bass_onset[np.clip(beats, 0, bass_onset.size - 1)]
    totals = [accents[phase::beats_per_bar].mean() for phase in range(beats_per_bar)]
    return int(np.argmax(totals))


def analyze_rhythm(onset: np.ndarray, bass_onset: np.ndarray, fps: float) -> dict:
    bpm = estimate_tempo(onset, fps)
    beats = track_beats(onset, fps, bpm)
    if beats.size >= 8:
        # Report the tempo implied by the tracked beats (least-squares slope of
        # beat time against beat number); beat frames are integers, so a
        # median spacing would round the tempo.
        period = np.polyfit(np.arange(beats.size), beats.astype(float), 1)[0]
        bpm = 60.0 * fps / period
    phase = estimate_downbeat_phase(bass_onset, beats)
    times = beats / fps
    return {
        "bpm": round(float(bpm), 1),
        "beats": [round(float(t), 3) for t in times],
        "downbeats": [round(float(t), 3) for t in times[phase::4]],
        "beats_per_bar": 4,
    }
