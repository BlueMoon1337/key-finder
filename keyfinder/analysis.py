"""Full-track analysis: key, tempo/beat grid and chords at every detail level."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from . import audio, chords, features, key, tempo


def chord_levels(y: np.ndarray, sr: int, beats: list[float], detected_key: dict,
                 tuning: float | None = None) -> dict[str, list[dict]]:
    """Chords at every detail level from ``y``: the mix, or better its harmonic stems."""
    fps = sr / features.HOP
    pitch = features.pitch_features(y, sr, tuning)
    chroma = features.clean_chroma(pitch["chroma"], fps)
    bass = features.clean_chroma(pitch["bass"], fps)
    beat_frames = np.round(np.asarray(beats) * fps).astype(int)
    return {
        level: chords.recognize(chroma, bass, beat_frames, fps, level=level, key=detected_key)
        for level in chords.LEVELS
    }


# Switching the bar's phase costs as much as this many chord changes off the downbeat, so it
# only happens when several changes in a row agree (see downbeats_from_chords).
PHASE_SWITCH_COST = 3.0


def downbeats_from_chords(beats: list[float], segments: list[dict], current: list[float],
                          beats_per_bar: int = 4) -> list[float]:
    """Downbeats placed where the chords change, section by section.

    Chords mostly change on the first beat of a bar, which is more reliable than the
    low-frequency accents the first guess comes from (a live mix can easily mislead those).
    The bar's phase may also shift partway through: the beat tracker keeps one tempo, so when
    a performer slows down or holds a note between sections it gains or loses a beat. A
    Viterbi pass over the chord changes picks a phase for each, paying PHASE_SWITCH_COST to
    change it, and the bars follow. Keeps ``current`` when there are too few changes.
    """
    if len(beats) < 2 * beats_per_bar:
        return current
    times = np.asarray(beats)
    events = []  # beat index of each chord change that lands on a beat
    for seg in segments[1:]:
        if seg["root"] is None:
            continue
        i = int(np.argmin(np.abs(times - seg["start"])))
        if abs(times[i] - seg["start"]) < 0.15:
            events.append(i)
    if len(events) < 8:
        return current

    # Viterbi over the events: state = which beat (mod beats_per_bar) is the downbeat.
    n, k = len(events), beats_per_bar
    miss = np.array([[0.0 if e % k == p else 1.0 for p in range(k)] for e in events])
    cost = miss[0].copy()
    back = np.zeros((n, k), dtype=int)
    switch = PHASE_SWITCH_COST * (1 - np.eye(k))
    for t in range(1, n):
        total = cost[:, None] + switch
        back[t] = total.argmin(axis=0)
        cost = total[back[t], np.arange(k)] + miss[t]
    phases = np.zeros(n, dtype=int)
    phases[-1] = int(cost.argmin())
    for t in range(n - 1, 0, -1):
        phases[t - 1] = back[t, phases[t]]

    current_phase = int(np.argmin(np.abs(times - current[0]))) % k if current else -1
    if len(set(phases.tolist())) == 1:
        # One phase for the whole song: move to it only when the chords clearly prefer it.
        votes = np.bincount([e % k for e in events], minlength=k)
        phase = int(phases[0])
        if phase == current_phase or votes[phase] < 0.4 * n or votes[phase] < 1.5 * votes[current_phase]:
            return current
        return [round(float(t), 3) for t in times[phase::k]]

    # Each beat takes the phase of the section it's in; a new section starts at its first change.
    starts = [events[t] for t in range(n) if t == 0 or phases[t] != phases[t - 1]]
    section_phase = [int(phases[t]) for t in range(n) if t == 0 or phases[t] != phases[t - 1]]
    bars = []
    for b in range(len(times)):
        section = max(0, int(np.searchsorted(starts, b, side="right")) - 1)
        if b % k == section_phase[section]:
            bars.append(b)
    # Where the phase shifts, stretch the last bar rather than leave a bar of a beat or two.
    kept = [b for i, b in enumerate(bars) if i + 1 == len(bars) or bars[i + 1] - b >= k or b == 0]
    return [round(float(times[b]), 3) for b in kept]


def analyze_signal(y: np.ndarray, sr: int = audio.ANALYSIS_SR) -> dict:
    fps = sr / features.HOP
    pitch = features.pitch_features(y, sr)
    onset = features.onset_strength(y, sr)
    bass_onset = features.onset_strength(y, sr, max_freq=200.0)
    rhythm = tempo.analyze_rhythm(onset, bass_onset, fps)

    detected = key.detect_key(pitch["chroma"])
    levels = chord_levels(y, sr, rhythm["beats"], detected, pitch["tuning"])
    refined = key.refine_with_chords(detected, levels["basic"])
    if refined["name"] != detected["name"]:
        levels = chord_levels(y, sr, rhythm["beats"], refined, pitch["tuning"])
    rhythm["downbeats"] = downbeats_from_chords(rhythm["beats"], levels["basic"], rhythm["downbeats"])
    return {
        "duration": round(y.size / sr, 3),
        "tuning_cents": round(100.0 * pitch["tuning"], 1),
        "key": refined,
        **rhythm,
        "chords": levels,
        "waveform": audio.waveform_peaks(y),
    }


def scale_tempo(result: dict, factor: float) -> dict:
    """The analysis with its tempo doubled (factor 2) or halved (0.5), for when the beat tracker
    has counted half or double time. Bars are found again from the chords.
    """
    beats = list(result["beats"])
    if factor == 2:
        new = sorted(beats + [round((a + b) / 2, 3) for a, b in zip(beats[:-1], beats[1:], strict=True)])
    elif factor == 0.5:
        # Keep the half of the beats that holds the most downbeats, so 2x then 0.5x is a round trip.
        downbeats = set(result["downbeats"])
        parity = max((0, 1), key=lambda p: sum(b in downbeats for b in beats[p::2]))
        new = beats[parity::2]
    else:
        raise ValueError("tempo can only be doubled or halved")
    if len(new) < 2:
        return result
    times = np.asarray(new)
    first = int(np.argmin(np.abs(times - result["downbeats"][0]))) if result["downbeats"] else 0
    current = [round(float(t), 3) for t in times[first % 4::4]]
    downbeats = downbeats_from_chords(new, result["chords"]["basic"], current)
    return {**result, "beats": new, "downbeats": downbeats, "bpm": round(result["bpm"] * factor, 1)}


def improve_with_stems(result: dict, stems: dict[str, np.ndarray], sr: int) -> dict:
    """The analysis redone with the separated stems: chords, then the key and downbeats they imply.

    Returns ``result`` unchanged when there are no harmonic stems (vocals and accompaniment only).
    """
    levels = chords_from_stems(result, stems, sr)
    if levels is None:
        return result
    refined = key.refine_with_chords(result["key"], levels["basic"])
    if refined["name"] != result["key"]["name"]:
        # Spell and weigh the chords for the key they turned out to be in.
        levels = chords_from_stems({**result, "key": refined}, stems, sr)
    downbeats = downbeats_from_chords(result["beats"], levels["basic"], result["downbeats"])
    return {**result, "key": refined, "chords": levels, "downbeats": downbeats}


def chords_from_stems(result: dict, stems: dict[str, np.ndarray], sr: int) -> dict[str, list[dict]] | None:
    """Re-read the chords from the separated harmonic parts (everything but vocals and drums).

    Drums add broadband energy and the melody adds passing notes, both of which blur chords
    in the full mix. Returns None when the separation has no harmonic stems (vocals and
    accompaniment only).
    """
    parts = [stems[name] for name in stems if name not in ("vocals", "drums", "accompaniment")]
    if not parts:
        return None
    harmonic = np.sum([np.atleast_2d(p).mean(axis=0) for p in parts], axis=0)
    if sr != audio.ANALYSIS_SR:
        from scipy.signal import resample_poly

        harmonic = resample_poly(harmonic, audio.ANALYSIS_SR, sr).astype(np.float32)
    tuning = result["tuning_cents"] / 100.0
    return chord_levels(harmonic, audio.ANALYSIS_SR, result["beats"], result["key"], tuning)


def analyze_file(path: str | Path) -> dict:
    return analyze_signal(audio.load(path, audio.ANALYSIS_SR), audio.ANALYSIS_SR)
