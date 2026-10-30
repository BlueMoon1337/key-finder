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


def _beats_bpm(times: np.ndarray, fallback: float) -> float:
    """The tempo the beats imply: the least-squares slope of beat time against beat number
    (beat times sit on whole frames, so a median spacing would round the tempo)."""
    if times.size < 8:
        return fallback
    return 60.0 / float(np.polyfit(np.arange(times.size), times, 1)[0])


def analyze_rhythm(onset: np.ndarray, bass_onset: np.ndarray, fps: float) -> dict:
    """Tempo, beats and downbeats, with a tempo section wherever the song changes tempo.

    The song's tempo is that of its first section, as a chart gives it; ``tempo_sections``
    lists each one. A song that keeps one tempo has one section, and its beats are tracked
    exactly as before.
    """
    sections = find_tempo_sections(onset, bass_onset, fps)
    duration = onset.size / fps
    if len(sections) == 1:
        bpm = estimate_tempo(onset, fps)
        beats = track_beats(onset, fps, bpm)
        times = beats / fps
        bpm = _beats_bpm(times, bpm)
        phase = estimate_downbeat_phase(bass_onset, beats)
        downbeats = times[phase::4]
        tempo_sections = [{"start": 0.0, "end": round(duration, 3), "bpm": round(bpm, 1)}]
    else:
        times, downbeats, tempo_sections = _track_sections(onset, bass_onset, fps, sections)
        bpm = tempo_sections[0]["bpm"]
    return {
        "bpm": round(float(bpm), 1),
        "beats": [round(float(t), 3) for t in times],
        "downbeats": [round(float(t), 3) for t in downbeats],
        "beats_per_bar": 4,
        "tempo_sections": tempo_sections,
    }


# ------------------------------------------------------------------ tempo changes
#
# The tempo is estimated in overlapping windows, folded into one octave (a window that hears
# the eighth notes, or half time, isn't a new tempo), and smoothed with a Viterbi pass that
# lets it drift but charges TEMPO_SWITCH to jump. A section that comes out of that at a new
# tempo is kept only if it is long enough, different enough, and its low end (kick and bass)
# beats to the new tempo more than to its neighbour's: a dotted-eighth guitar delay, a triplet
# feel or a busy fill sound like another tempo higher up, but the kick and bass stay put.

TEMPO_WINDOW = 12.0  # seconds per window
TEMPO_HOP = 3.0
TEMPO_STEPS = 96  # steps per octave of the folded tempo grid
TEMPO_DRIFT = 2  # free movement per window, in steps (about 1.5 %)
TEMPO_SWITCH = 4.0  # the cost of a jump, in windows that prefer the new tempo outright
MIN_TEMPO_SECTION = 30.0  # seconds
MIN_TEMPO_CHANGE = 0.10  # as a log ratio, octaves aside: about 10 %
NEW_TEMPO_EVIDENCE = 1.3  # the new tempo must be this much stronger than the neighbour's...
NEW_TEMPO_BASS_EVIDENCE = 1.5  # ...and this much in the low end


def _octave_distance(a: float, b: float) -> float:
    """How far apart two tempos are, octaves aside, as a log ratio."""
    r = np.log2(a / b)
    return float(abs(r - round(r)) * np.log(2))


def _family_strength(bpms: np.ndarray, strength: np.ndarray, bpm: float) -> float:
    """How strongly a stretch beats at ``bpm``, at half or at double it."""
    return max(float(np.interp(bpm * r, bpms, strength, left=0, right=0)) for r in (1, 2, 0.5))


def _window_path(onset: np.ndarray, fps: float, center: float) -> tuple[np.ndarray, np.ndarray]:
    """The folded tempo of each window (Viterbi-smoothed) and the windows' start times."""
    from scipy.ndimage import maximum_filter1d

    win, hop = int(TEMPO_WINDOW * fps), int(TEMPO_HOP * fps)
    starts = np.arange(0, max(1, onset.size - win + 1), hop)
    grid = center / np.sqrt(2) * 2 ** (np.arange(TEMPO_STEPS) / TEMPO_STEPS)
    emissions = np.zeros((starts.size, TEMPO_STEPS))
    for i, s in enumerate(starts):
        bpms, strength = tempo_strength(onset[s:s + win], fps)
        for k in (-1, 0, 1):
            emissions[i] = np.maximum(emissions[i], np.interp(grid * 2.0 ** k, bpms, strength, left=0, right=0))
    emissions /= emissions.max(axis=1, keepdims=True) + 1e-12
    # Viterbi: drift freely by TEMPO_DRIFT steps (the grid wraps: it's one octave), jump at a cost.
    offsets = np.arange(-TEMPO_DRIFT, TEMPO_DRIFT + 1)
    score = emissions[0].copy()
    back = np.zeros(emissions.shape, dtype=int)
    idx = np.arange(TEMPO_STEPS)
    for t in range(1, starts.size):
        neighbours = score[(idx[:, None] + offsets[None, :]) % TEMPO_STEPS]
        near = maximum_filter1d(score, 2 * TEMPO_DRIFT + 1, mode="wrap")
        near_from = (idx + offsets[np.argmax(neighbours, axis=1)]) % TEMPO_STEPS
        jump = score.max() - TEMPO_SWITCH
        back[t] = np.where(jump > near, int(score.argmax()), near_from)
        score = np.maximum(near, jump) + emissions[t]
    path = np.zeros(starts.size, dtype=int)
    path[-1] = int(score.argmax())
    for t in range(starts.size - 1, 0, -1):
        path[t - 1] = back[t, path[t]]
    return grid[path], starts / fps


def find_tempo_sections(onset: np.ndarray, bass_onset: np.ndarray, fps: float) -> list[dict]:
    """Where the tempo changes: ``[{"start", "end", "bpm"}]``, one section for a steady song.

    The bpm here is a rough one, in the octave the beat tracker should use; the beats tracked
    in each section give the exact tempo.
    """
    duration = onset.size / fps
    main = estimate_tempo(onset, fps)
    if duration < 2 * MIN_TEMPO_SECTION + TEMPO_WINDOW:
        return [{"start": 0.0, "end": duration, "bpm": main}]
    tempos, starts = _window_path(onset, fps, main)

    # Runs of windows at one tempo, split at the middle of the windows' overlap.
    runs: list[list[float]] = [[0.0, 0.0, tempos[0], 1]]
    for t, s in zip(tempos[1:], starts[1:], strict=True):
        run = runs[-1]
        if _octave_distance(t, run[2]) > MIN_TEMPO_CHANGE / 2:
            runs.append([s + TEMPO_WINDOW / 2, 0.0, t, 1])
        else:
            t *= 2.0 ** round(np.log2(run[2] / t))  # the grid wraps: same octave as the run
            run[2] = (run[2] * run[3] + t) / (run[3] + 1)
            run[3] += 1
    for a, b in zip(runs, runs[1:], strict=False):
        a[1] = b[0]
    runs[-1][1] = duration
    sections = [[s, e, t] for s, e, t, _ in runs]

    def keep(i: int, j: int) -> bool:
        """Whether section i is a tempo of its own rather than neighbour j's."""
        s, e, t = sections[i]
        if e - s < MIN_TEMPO_SECTION or _octave_distance(t, sections[j][2]) < MIN_TEMPO_CHANGE:
            return False
        a, z = int(s * fps), int(e * fps)
        for env, needed in ((onset, NEW_TEMPO_EVIDENCE), (bass_onset, NEW_TEMPO_BASS_EVIDENCE)):
            bpms, strength = tempo_strength(env[a:z], fps)
            if _family_strength(bpms, strength, t) < needed * _family_strength(bpms, strength, sections[j][2]):
                return False
        return True

    # Fold doubtful sections into their closest neighbour, shortest first, until all stand.
    while len(sections) > 1:
        for i in sorted(range(len(sections)), key=lambda i: sections[i][1] - sections[i][0]):
            others = [j for j in (i - 1, i + 1) if 0 <= j < len(sections)]
            j = min(others, key=lambda j: _octave_distance(sections[j][2], sections[i][2]))
            if not keep(i, j):
                a, b = sorted((i, j))
                longer = max((i, j), key=lambda k: sections[k][1] - sections[k][0])
                sections[a:b + 1] = [[sections[a][0], sections[b][1], sections[longer][2]]]
                break
        else:
            break

    if len(sections) == 1:
        return [{"start": 0.0, "end": duration, "bpm": main}]
    # Each tempo in the octave its own section's estimate is in: the whole song's estimate can
    # land on a tempo that suits both halves (60 for a song that goes from 90 to 120).
    out = []
    for s, e, t in sections:
        own = estimate_tempo(onset[int(s * fps):int(e * fps)], fps)
        out.append({"start": float(s), "end": float(e), "bpm": float(t * 2.0 ** round(np.log2(own / t)))})
    return out


def _track_sections(onset: np.ndarray, bass_onset: np.ndarray, fps: float, sections: list[dict]):
    """Beats tracked section by section, each at its own tempo; (beats, downbeats, sections)."""
    margin = int(4 * fps)  # a little past each edge, so the tracker settles before the section starts
    beats: list[float] = []
    downbeats: list[float] = []
    out = []
    for sec in sections:
        a, z = int(sec["start"] * fps), int(sec["end"] * fps)
        lo, hi = max(0, a - margin), min(onset.size, z + margin)
        found = track_beats(onset[lo:hi], fps, sec["bpm"]) + lo
        times = found[(found >= a) & (found < z)] / fps
        period = 60.0 / sec["bpm"]
        if beats and times.size and times[0] - beats[-1] < 0.5 * period:
            times = times[1:]  # the previous section's last beat is this one's first
        frames = np.round(times * fps).astype(int)
        phase = estimate_downbeat_phase(bass_onset, frames) if frames.size >= 8 else 0
        beats.extend(times.tolist())
        downbeats.extend(times[phase::4].tolist())
        out.append({"start": round(sec["start"], 3), "end": round(sec["end"], 3),
                    "bpm": round(_beats_bpm(times, sec["bpm"]), 1)})
    return np.asarray(beats), np.asarray(downbeats), out


def sections_from_beats(beats: list[float]) -> list[dict]:
    """Tempo sections of a beat grid that's known to be right (a click track's).

    Splits where the beats' tempo changes by MIN_TEMPO_CHANGE or more for MIN_TEMPO_SECTION,
    the best split first; a steady grid is one section.
    """
    times = np.asarray(beats, dtype=float)
    if times.size < 16:
        return [{"start": 0.0, "end": float(times[-1]) if times.size else 0.0,
                 "bpm": round(_beats_bpm(times, 120.0), 1)}]
    gaps = np.diff(times)
    # Each beat's local tempo: the median spacing around it, so a missed or doubled click doesn't count.
    local = np.array([np.median(gaps[max(0, i - 4): i + 4]) for i in range(gaps.size)])
    logs = np.log(60.0 / local)

    cum, cum2 = np.concatenate([[0], np.cumsum(logs)]), np.concatenate([[0], np.cumsum(logs ** 2)])

    def sse(a: int, b: int) -> float:  # squared error of logs[a:b] about its mean
        n = b - a
        return float(cum2[b] - cum2[a] - (cum[b] - cum[a]) ** 2 / n) if n else 0.0

    def split(a: int, b: int) -> list[int]:
        """The change point in logs[a:b] that best explains it as two tempos, recursively."""
        best, at = sse(a, b), None
        for k in range(a + 1, b):
            if times[k] - times[a] < MIN_TEMPO_SECTION or times[b] - times[k] < MIN_TEMPO_SECTION:
                continue
            cost = sse(a, k) + sse(k, b)
            if cost < best:
                best, at = cost, k
        if at is None or abs(float(np.median(logs[a:at]) - np.median(logs[at:b]))) < MIN_TEMPO_CHANGE:
            return []
        return [*split(a, at), at, *split(at, b)]

    cuts = [0, *split(0, gaps.size), gaps.size]
    return [{"start": round(float(times[a]), 3), "end": round(float(times[b]), 3),
             "bpm": round(_beats_bpm(times[a:b + 1], 60.0 / float(np.median(gaps[a:b]))), 1)}
            for a, b in zip(cuts, cuts[1:], strict=False)]


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
            # The tempo where the click stopped: the clicks just before, as the song may change tempo.
            recent = np.diff(times[max(0, i - 9):i])
            local = float(np.median(recent)) if recent.size else period
            missing = int(round(gap / local)) - 1
            if missing > 0 and gap > 1.6 * local:  # the click stopped for a while
                step = gap / (missing + 1)
                for _ in range(missing):
                    beats.append(beats[-1] + step)
                    accented.append(False)
        beats.append(float(t))
        accented.append(bool(accents[i]) if accents is not None else False)
    beats_arr = np.asarray(beats)
    slope = np.polyfit(np.arange(beats_arr.size), beats_arr, 1)[0]
    sections = sections_from_beats(beats)
    bpm = sections[0]["bpm"] if len(sections) > 1 else round(60.0 / slope, 1)
    sections[0]["start"], sections[-1]["end"] = 0.0, max(sections[-1]["end"], round(beats[-1], 3))
    result = {"bpm": bpm, "beats": [round(b, 3) for b in beats], "downbeats": None, "beats_per_bar": 4,
              "tempo_sections": sections}
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
