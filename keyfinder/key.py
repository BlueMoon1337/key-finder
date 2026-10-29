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


# How chords sit in a key: the usual weight of each chord, by its root above the tonic and
# whether it's major or minor. Common practice, not corpus statistics: in major, I then IV and
# V, then vi, ii, iii and a borrowed bVII; in minor, i, then the VI and VII that minor songs
# lean on, iv, V (from the harmonic minor), III and v.
MAJOR_KEY_CHORDS = {(0, "maj"): 1.0, (5, "maj"): 0.6, (7, "maj"): 0.6, (9, "min"): 0.45, (2, "min"): 0.3,
                    (4, "min"): 0.15, (10, "maj"): 0.1}
MINOR_KEY_CHORDS = {(0, "min"): 1.0, (8, "maj"): 0.5, (10, "maj"): 0.5, (5, "min"): 0.45, (7, "maj"): 0.4,
                    (3, "maj"): 0.4, (7, "min"): 0.25}
# How much the chord fit counts against the pitch-class profile, and the nudge for a key whose
# home chord starts or ends the song.
KEY_CHORD_WEIGHT = 1.5
FIRST_LAST_BONUS = 0.05
_TRIAD = {"maj": "maj", "7": "maj", "maj7": "maj", "min": "min", "min7": "min"}


def chord_fit(durations: dict[tuple[int, str], float], tonic: int, mode: str) -> float:
    """Cosine similarity between a song's chord time (by root and major/minor) and a key's usual chords."""
    template = MAJOR_KEY_CHORDS if mode == "major" else MINOR_KEY_CHORDS
    weights = np.array(list(template.values()))
    used = np.array([durations.get(((r + tonic) % 12, q), 0.0) for r, q in template])
    norm = np.sqrt(sum(v * v for v in durations.values())) * np.linalg.norm(weights)
    return float(used @ weights / norm) if norm else 0.0


def refine_with_chords(key: dict, segments: list[dict]) -> dict:
    """Choose the key using the chord sequence as well as the pitch-class profile.

    Profiles mislead in two common ways: relative keys share every note (B minor and D major),
    and minor songs that lean on their VII and VI chords (Fm - Eb - Db) or use a major V (A in
    D minor) pull the profile towards another key. So a key's profile score is the better of
    its own and its relative's, and the chords decide: each key adds KEY_CHORD_WEIGHT times how
    well the song's chord time fits that key's usual chords (chord_fit), plus a nudge when its
    home chord starts or ends the song.
    """
    chords = [s for s in segments if s.get("root") is not None]
    if not chords or not key.get("profile"):
        return key
    durations: dict[tuple[int, str], float] = {}
    for seg in chords:
        triad = (seg["root"], _TRIAD.get(seg["quality"], seg["quality"]))
        durations[triad] = durations.get(triad, 0.0) + seg["end"] - seg["start"]
    scores = key_scores(np.asarray(key["profile"], dtype=float))

    def profile(tonic: int, mode: str) -> float:
        rel_tonic, rel_mode = relative_key(tonic, mode)
        return max(scores[0 if mode == "major" else 1, tonic], scores[0 if rel_mode == "major" else 1, rel_tonic])

    def is_home(seg: dict, tonic: int, mode: str) -> bool:
        return seg["root"] == tonic and _TRIAD.get(seg["quality"]) == ("min" if mode == "minor" else "maj")

    def total(tonic: int, mode: str) -> float:
        ends = is_home(chords[0], tonic, mode) + is_home(chords[-1], tonic, mode)
        return profile(tonic, mode) + KEY_CHORD_WEIGHT * chord_fit(durations, tonic, mode) + FIRST_LAST_BONUS * ends

    best = max(((tonic, mode) for mode in ("major", "minor") for tonic in range(12)), key=lambda k: total(*k))
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
