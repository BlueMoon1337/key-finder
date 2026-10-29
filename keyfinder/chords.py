"""Chord recognition: beat-synchronous chroma, template matching and Viterbi smoothing."""

from __future__ import annotations

import itertools

import numpy as np

from .key import PITCH_CLASSES_FLAT, PITCH_CLASSES_SHARP, scale_pitch_classes

# Intervals above the root, plus a small prior penalty so richer chords only
# win when the extra notes are clearly present.
QUALITIES = {
    "maj": ((0, 4, 7), 0.0),
    "min": ((0, 3, 7), 0.0),
    "7": ((0, 4, 7, 10), 0.06),
    "maj7": ((0, 4, 7, 11), 0.09),  # higher: the 5th overtone of the fifth is the major 7th
    "min7": ((0, 3, 7, 10), 0.06),
    "dim": ((0, 3, 6), 0.06),
    "aug": ((0, 4, 8), 0.08),
    "sus2": ((0, 2, 7), 0.07),
    "sus4": ((0, 5, 7), 0.07),
}
LEVELS = {
    "basic": ("maj", "min"),
    "intermediate": ("maj", "min", "7", "maj7", "min7"),
    "advanced": tuple(QUALITIES),
}
SUFFIX = {"maj": "", "min": "m", "7": "7", "maj7": "maj7", "min7": "m7",
          "dim": "dim", "aug": "aug", "sus2": "sus2", "sus4": "sus4"}
NO_CHORD = "N"
# How much a bass note matching the root counts towards a chord.
BASS_WEIGHT = 0.2
# How well a chord must match before "no chord" (N) is preferred, outside silences.
NO_CHORD_SCORE = 0.35
# Only silences at least this long are "no chord"; the chord carries over shorter rests and stops.
MIN_SILENCE_SECONDS = 2.0
# A bass note on the chord's third or fifth (an inversion, e.g. G/B) counts this share of that.
INVERSION_SHARE = 0.8
# The bass note must hold this share of a chord's bass energy to be written as a slash chord.
SLASH_MIN_SHARE = 0.4
# Detail levels that write inversions as slash chords (G/B); "basic" keeps plain chords.
SLASH_LEVELS = ("intermediate", "advanced")


def chord_label(root: int | None, quality: str | None, flats: bool = False, bass: int | None = None) -> str:
    if root is None or quality is None:
        return NO_CHORD
    names = PITCH_CLASSES_FLAT if flats else PITCH_CLASSES_SHARP
    label = names[root % 12] + SUFFIX[quality]
    return f"{label}/{names[bass % 12]}" if bass is not None and bass % 12 != root % 12 else label


def chord_pitch_classes(root: int, quality: str) -> set[int]:
    return {(root + i) % 12 for i in QUALITIES[quality][0]}


def _vocabulary(level: str) -> list[tuple[int, str]]:
    return [(root, q) for q in LEVELS[level] for root in range(12)]


def _templates(vocab: list[tuple[int, str]]) -> np.ndarray:
    t = np.zeros((len(vocab), 12))
    for i, (root, quality) in enumerate(vocab):
        intervals = QUALITIES[quality][0]
        for k, interval in enumerate(intervals):
            # Root and fifth carry the most energy in real recordings.
            t[i, (root + interval) % 12] = {0: 1.0, 7: 0.9}.get(interval, 0.8 if k < 3 else 0.6)
    return t / np.linalg.norm(t, axis=1, keepdims=True)


def sync_to_beats(features: np.ndarray, beat_frames: np.ndarray, n_frames: int) -> tuple[np.ndarray, np.ndarray]:
    """Median feature per inter-beat segment; returns (segments, boundaries in frames)."""
    bounds = np.unique(np.concatenate(([0], np.clip(beat_frames, 0, n_frames), [n_frames])))
    segments = np.stack([
        np.median(features[:, a:b], axis=1) if b > a else features[:, min(a, n_frames - 1)]
        for a, b in itertools.pairwise(bounds)
    ], axis=1)
    return segments, bounds


IN_KEY_BONUS = 0.05


def key_prior(vocab: list[tuple[int, str]], key: dict) -> np.ndarray:
    """A small bonus for chords that belong to the key.

    In a minor key the chord on the fifth is usually major (A or A7 in D minor, from the
    harmonic minor scale), so it gets the full bonus; the natural-minor v (Am) gets half,
    for modal songs. Without this, a fifth chord with no third (A and E only) reads as Am.
    """
    tonic, mode = key["tonic"], key["mode"]
    diatonic = scale_pitch_classes(tonic, mode)
    dominant = (tonic + 7) % 12
    bonus = np.zeros(len(vocab))
    for i, (root, quality) in enumerate(vocab):
        if mode == "minor" and root == dominant:
            bonus[i] = IN_KEY_BONUS if quality in ("maj", "7") else IN_KEY_BONUS / 2 * (quality in ("min", "min7"))
        elif chord_pitch_classes(root, quality) <= diatonic:
            bonus[i] = IN_KEY_BONUS
    return bonus


def recognize(
    chroma: np.ndarray,
    bass: np.ndarray,
    beat_frames: np.ndarray,
    fps: float,
    level: str = "intermediate",
    key: dict | None = None,
    self_transition: float = 0.7,
) -> list[dict]:
    """Chord segments ``{start, end, root, quality, bass, label}`` covering the track.

    ``bass`` is set (and the label is a slash chord, e.g. G/B) when another chord tone
    is clearly in the bass, at the levels in SLASH_LEVELS.
    """
    n_frames = chroma.shape[1]
    if n_frames == 0:
        return []
    if beat_frames.size < 2:
        # Without a beat grid fall back to half-second segments.
        beat_frames = np.arange(0, n_frames, max(1, int(fps / 2)))
    seg_chroma, bounds = sync_to_beats(chroma, beat_frames, n_frames)
    seg_bass, _ = sync_to_beats(bass, beat_frames, n_frames)

    vocab = _vocabulary(level)
    templates = _templates(vocab)
    energy = seg_chroma.sum(axis=0)
    norm = seg_chroma / np.maximum(np.linalg.norm(seg_chroma, axis=0, keepdims=True), 1e-9)
    similarity = templates @ norm  # (chords, segments)

    penalty = np.array([QUALITIES[q][1] for _, q in vocab])
    similarity -= penalty[:, None]
    # A strong bass note on the root makes that chord more likely; on its third or fifth
    # (an inversion such as G/B) a little less so.
    bass_norm = seg_bass / np.maximum(seg_bass.sum(axis=0, keepdims=True), 1e-9)
    roots = np.array([r for r, _ in vocab])
    others = [[(r + i) % 12 for i in QUALITIES[q][0][1:3]] for r, q in vocab]
    inversion = np.stack([bass_norm[o].max(axis=0) for o in others])
    similarity += BASS_WEIGHT * np.maximum(bass_norm[roots], INVERSION_SHARE * inversion)
    if key is not None:
        similarity += key_prior(vocab, key)[:, None]

    # "No chord" for real silences. A short rest (a stop, a gap between hits) carries no evidence
    # either way, so the smoothing below carries the chord over it, as a chord chart would.
    quiet = energy < 0.05 * (np.percentile(energy, 95) + 1e-9)
    silent = np.zeros_like(quiet)
    seconds = np.diff(bounds) / fps
    start = None
    for i, q in enumerate([*quiet, False]):
        if q and start is None:
            start = i
        elif not q and start is not None:
            if seconds[start:i].sum() >= MIN_SILENCE_SECONDS:
                silent[start:i] = True
            start = None
    similarity[:, quiet & ~silent] = 0.0
    nc_score = np.where(silent, 1.5, np.where(quiet, -1.0, NO_CHORD_SCORE))
    similarity = np.vstack([similarity, nc_score])

    states = similarity.shape[0]
    log_emit = 15.0 * similarity  # sharpen the softmax over chord candidates
    log_emit -= np.logaddexp.reduce(log_emit, axis=0, keepdims=True)
    # Weight evidence by duration (relative to a 120 BPM beat) so smoothing
    # behaves the same whether the beat grid is fast, slow or missing.
    durations = np.diff(bounds) / fps
    log_emit *= np.clip(durations / 0.5, 0.25, 4.0)[None, :]
    stay = np.log(self_transition)
    # Spread the change probability over a fixed 24 chords rather than the
    # whole vocabulary, so a larger vocabulary does not make changes costlier.
    move = np.log((1 - self_transition) / 24)
    trans = np.full((states, states), move)
    np.fill_diagonal(trans, stay)

    n_seg = log_emit.shape[1]
    score = log_emit[:, 0] - np.log(states)
    back = np.zeros((states, n_seg), dtype=int)
    for t in range(1, n_seg):
        cand = score[:, None] + trans
        back[:, t] = np.argmax(cand, axis=0)
        score = cand[back[:, t], np.arange(states)] + log_emit[:, t]
    path = np.zeros(n_seg, dtype=int)
    path[-1] = int(np.argmax(score))
    for t in range(n_seg - 1, 0, -1):
        path[t - 1] = back[path[t], t]

    flats = bool(key.get("flats")) if key else False
    segments: list[dict] = []
    spans: list[list[int]] = []  # the beat segments each chord covers
    for i, state in enumerate(path):
        start, end = bounds[i] / fps, bounds[i + 1] / fps
        root, quality = (None, None) if state == len(vocab) else vocab[state]
        if segments and segments[-1]["root"] == root and segments[-1]["quality"] == quality:
            segments[-1]["end"] = round(end, 3)
            spans[-1].append(i)
            continue
        segments.append({"start": round(start, 3), "end": round(end, 3), "root": root, "quality": quality})
        spans.append([i])

    bass_level = np.percentile(seg_bass.sum(axis=0), 95) + 1e-9
    for seg, span in zip(segments, spans, strict=True):
        seg["bass"] = None
        if level in SLASH_LEVELS and seg["root"] is not None:
            # The chord's bass note over its whole span, when one clearly dominates.
            profile = seg_bass[:, span].sum(axis=1)
            note = int(profile.argmax())
            clear = profile[note] >= SLASH_MIN_SHARE * profile.sum()
            audible = profile.sum() / len(span) >= 0.1 * bass_level
            if clear and audible and note != seg["root"] and note in chord_pitch_classes(seg["root"], seg["quality"]):
                seg["bass"] = note
        seg["label"] = chord_label(seg["root"], seg["quality"], flats, seg["bass"])
    return segments
