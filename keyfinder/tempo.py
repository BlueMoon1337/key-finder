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


# ------------------------------------------------------------------ click tracks

CLICK_MIN_GAP = 0.12  # seconds between clicks, at least (500 BPM)


def _click_onsets(y: np.ndarray, sr: int) -> np.ndarray:
    """Sample positions where each click starts: a click track is silence and short ticks."""
    hop = 64
    n = y.size // hop
    if n < 4:
        return np.zeros(0, dtype=int)
    env = np.abs(y[: n * hop]).reshape(n, hop).max(axis=1)
    loud = np.percentile(env, 99.5)
    if loud <= 1e-4:
        return np.zeros(0, dtype=int)
    above = env > 0.2 * loud
    starts = np.flatnonzero(above & ~np.concatenate([[False], above[:-1]]))
    out, last = [], -10**9
    gap = int(CLICK_MIN_GAP * sr)
    for f in starts:
        s = f * hop
        if s - last < gap:
            continue
        # The first sample over a fifth of this click's peak, for sample-accurate timing.
        window = np.abs(y[max(0, s - hop): s + 4 * hop])
        first = int(np.argmax(window > 0.2 * window.max()))
        out.append(max(0, s - hop) + first)
        last = out[-1]
    return np.asarray(out, dtype=int)


def _accents(y: np.ndarray, sr: int, onsets: np.ndarray) -> np.ndarray | None:
    """Which clicks are accented (MultiTracks' and most clicks mark beat one with a higher or
    louder tick), or None when they all sound alike."""
    length = int(0.03 * sr)
    feats = []
    window = np.hanning(length)
    freqs = np.fft.rfftfreq(length, 1 / sr)
    for s in onsets:
        seg = y[s:s + length]
        if seg.size < length:
            seg = np.pad(seg, (0, length - seg.size))
        spec = np.abs(np.fft.rfft(seg * window))
        feats.append((float((spec * freqs).sum() / (spec.sum() + 1e-12)), float(np.abs(seg).max())))
    for values in (np.log([f[0] + 1 for f in feats]), np.log([f[1] + 1e-6 for f in feats])):
        lo, hi = np.percentile(values, 5), np.percentile(values, 95)
        if hi - lo < 0.05:
            continue
        high = values > (lo + hi) / 2
        share = high.mean()
        # Two clear groups, the accented one a bar's worth (1 in 2 to 1 in 8) of the clicks.
        spread = max(values[high].std(), values[~high].std()) if 0 < share < 1 else 1
        if 1 / 8.5 <= share <= 1 / 1.9 and (hi - lo) > 4 * spread:
            return high
    return None


def beats_from_click(y: np.ndarray, sr: int, bpm_hint: float | None = None) -> dict | None:
    """The beat grid a click track plays: every click a beat, accented clicks the downbeats.

    Clicks on eighths (a slow song's click) are thinned to the beat when ``bpm_hint`` (e.g. a
    MultiTracks name's BPM) says so; gaps where the click stops are filled at the tempo around
    them. None when there aren't enough clicks to go on.
    """
    onsets = _click_onsets(np.asarray(y, dtype=np.float32), sr)
    if onsets.size < 8:
        return None
    accents = _accents(y, sr, onsets)
    times = onsets / sr
    period = float(np.median(np.diff(times)))
    if bpm_hint:
        ratio = (60.0 / bpm_hint) / period
        if 1.7 < ratio < 2.3:  # eighth-note clicks: keep the half that holds the accents
            keep = 0
            if accents is not None:
                keep = int(np.argmax([accents[p::2].sum() for p in (0, 1)]))
            times, accents = times[keep::2], (accents[keep::2] if accents is not None else None)
            period *= 2
    beats, accented = [], []
    for i, t in enumerate(times):
        if beats:
            gap = t - beats[-1]
            missing = int(round(gap / period)) - 1
            if missing > 0 and gap > 1.6 * period:  # the click stopped for a while
                step = gap / (missing + 1)
                for _ in range(missing):
                    beats.append(beats[-1] + step)
                    accented.append(False)
        beats.append(float(t))
        accented.append(bool(accents[i]) if accents is not None else False)
    beats_arr = np.asarray(beats)
    slope = np.polyfit(np.arange(beats_arr.size), beats_arr, 1)[0]
    result = {"bpm": round(60.0 / slope, 1), "beats": [round(b, 3) for b in beats], "downbeats": None,
              "beats_per_bar": 4}
    if accents is not None:
        idx = np.flatnonzero(accented)
        if idx.size >= 2:
            per_bar = int(np.bincount(np.diff(idx)).argmax())
            if 2 <= per_bar <= 12:
                # Keep counting bars where the click stopped (no accents there to go by).
                downs, last = [], None
                for i in range(len(beats)):
                    if accented[i] or (last is not None and i - last == per_bar
                                       and not any(accented[i + 1:i + 2])):
                        downs.append(i)
                        last = i
                result["downbeats"] = [round(beats[i], 3) for i in downs]
                result["beats_per_bar"] = per_bar
    return result
