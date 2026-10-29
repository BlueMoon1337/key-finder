"""Musical key estimation by correlating chroma with key profiles."""

from __future__ import annotations

import numpy as np

PITCH_CLASSES_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
PITCH_CLASSES_FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
# Conventional tonic spellings: Db major rather than C# major, but C# minor.
MAJOR_TONIC = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
MINOR_TONIC = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B"]
# Keys whose signature uses flats (by tonic pitch class).
FLAT_MAJOR = {1, 3, 5, 8, 10}
FLAT_MINOR = {0, 2, 3, 5, 7, 10}

# Krumhansl & Kessler (1982) probe-tone ratings.
KRUMHANSL_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KRUMHANSL_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
# Temperley (2007), from the Kostka-Payne corpus.
TEMPERLEY_MAJOR = np.array([0.748, 0.060, 0.488, 0.082, 0.670, 0.460, 0.096, 0.715, 0.104, 0.366, 0.057, 0.400])
TEMPERLEY_MINOR = np.array([0.712, 0.084, 0.474, 0.618, 0.049, 0.460, 0.105, 0.747, 0.404, 0.067, 0.133, 0.330])

MAJOR_SCALE = (0, 2, 4, 5, 7, 9, 11)
NATURAL_MINOR_SCALE = (0, 2, 3, 5, 7, 8, 10)


def key_name(tonic: int, mode: str) -> str:
    names = MAJOR_TONIC if mode == "major" else MINOR_TONIC
    return f"{names[tonic % 12]} {mode}"


def uses_flats(tonic: int, mode: str) -> bool:
    return (tonic % 12) in (FLAT_MAJOR if mode == "major" else FLAT_MINOR)


def camelot(tonic: int, mode: str) -> str:
    """Camelot wheel code used by DJs for harmonic mixing (C major = 8B, A minor = 8A)."""
    relative_major = tonic % 12 if mode == "major" else (tonic + 3) % 12
    number = (8 + 7 * relative_major) % 12 or 12
    return f"{number}{'B' if mode == 'major' else 'A'}"


def relative_key(tonic: int, mode: str) -> tuple[int, str]:
    return ((tonic + 9) % 12, "minor") if mode == "major" else ((tonic + 3) % 12, "major")


def scale_pitch_classes(tonic: int, mode: str) -> set[int]:
    steps = MAJOR_SCALE if mode == "major" else NATURAL_MINOR_SCALE
    return {(tonic + s) % 12 for s in steps}


def _zscore(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    sd = v.std()
    return (v - v.mean()) / sd if sd > 0 else v * 0.0


def key_scores(profile: np.ndarray) -> np.ndarray:
    """Correlation of a 12-bin profile with all 24 keys: rows major/minor, columns tonic."""
    p = _zscore(profile)
    scores = np.zeros((2, 12))
    for row, templates in enumerate(((KRUMHANSL_MAJOR, TEMPERLEY_MAJOR), (KRUMHANSL_MINOR, TEMPERLEY_MINOR))):
        for template in templates:
            t = _zscore(template)
            for tonic in range(12):
                scores[row, tonic] += np.dot(p, np.roll(t, tonic)) / 12.0
        scores[row] /= len(templates)
    return scores


def global_profile(chroma: np.ndarray) -> np.ndarray:
    """Average chroma, weighting each frame by its loudness so silence does not count."""
    energy = chroma.sum(axis=0)
    if energy.sum() <= 0:
        return np.zeros(12)
    norm = chroma / np.maximum(chroma.max(axis=0, keepdims=True), 1e-9)
    return (norm * energy).sum(axis=1) / energy.sum()


def detect_key(chroma: np.ndarray) -> dict:
    """Most likely key with a confidence in [0, 1] and the runner-up candidates."""
    profile = global_profile(chroma)
    scores = key_scores(profile)
    order = np.argsort(scores, axis=None)[::-1]
    candidates = []
    for flat_index in order[:5]:
        row, tonic = divmod(int(flat_index), 12)
        mode = "major" if row == 0 else "minor"
        candidates.append({
            "tonic": tonic,
            "mode": mode,
            "name": key_name(tonic, mode),
            "score": round(float(scores[row, tonic]), 4),
        })
    best, second = candidates[0], candidates[1]
    # The margin over the runner-up is a better confidence signal than the raw
    # correlation; relative major/minor are inherently close, so scale gently.
    margin = best["score"] - second["score"]
    confidence = float(np.clip(0.5 * max(best["score"], 0.0) + 2.5 * margin, 0.0, 1.0))
    rel_tonic, rel_mode = relative_key(best["tonic"], best["mode"])
    return {
        "tonic": best["tonic"],
        "mode": best["mode"],
        "name": best["name"],
        "camelot": camelot(best["tonic"], best["mode"]),
        "relative": key_name(rel_tonic, rel_mode),
        "flats": uses_flats(best["tonic"], best["mode"]),
        "confidence": round(confidence, 3),
        "candidates": candidates,
        "profile": [round(float(v), 4) for v in profile / (profile.max() or 1.0)],
    }


# How much time on a key's home chord counts against the pitch-class profile (see refine_with_chords).
KEY_CHORD_WEIGHT = 1.5


def refine_with_chords(key: dict, segments: list[dict]) -> dict:
    """Choose the key using the chord sequence as well as the pitch-class profile.

    Profiles can mislead: relative keys share every note (B minor and D major), and a minor
    song's major dominant (A in D minor) pulls towards the key a fifth up. But songs dwell
    on, start on and end on their home chord. Every key is scored by its profile match plus
    KEY_CHORD_WEIGHT times its home chord's share of the song (and a little for being the
    first or last chord); the best one wins.
    """
    chords = [s for s in segments if s.get("root") is not None]
    if not chords or not key.get("profile"):
        return key
    total = sum(s["end"] - s["start"] for s in chords) or 1.0

    def tonic_weight(tonic: int, mode: str) -> float:
        def is_tonic(seg: dict) -> bool:
            minor = seg["quality"] in ("min", "min7")
            return seg["root"] == tonic and minor == (mode == "minor")
        weight = sum(s["end"] - s["start"] for s in chords if is_tonic(s)) / total
        return weight + 0.15 * is_tonic(chords[0]) + 0.15 * is_tonic(chords[-1])

    scores = key_scores(np.asarray(key["profile"], dtype=float))
    best = max(
        ((tonic, mode) for mode in ("major", "minor") for tonic in range(12)),
        key=lambda k: scores[0 if k[1] == "major" else 1, k[0]] + KEY_CHORD_WEIGHT * tonic_weight(*k),
    )
    if best == (key["tonic"], key["mode"]):
        return key
    tonic, mode = best
    rel_tonic, rel_mode = relative_key(tonic, mode)
    refined = dict(key)
    refined.update({
        "tonic": tonic,
        "mode": mode,
        "name": key_name(tonic, mode),
        "camelot": camelot(tonic, mode),
        "relative": key_name(rel_tonic, rel_mode),
        "flats": uses_flats(tonic, mode),
    })
    return refined
