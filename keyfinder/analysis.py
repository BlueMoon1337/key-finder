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


def downbeats_from_chords(beats: list[float], segments: list[dict], current: list[float],
                         beats_per_bar: int = 4) -> list[float]:
    """Downbeats moved to where the chords change, when the chords say so clearly.

    Chords mostly change on the first beat of a bar, which is more reliable than the
    low-frequency accents the first guess comes from (a live mix can easily mislead those).
    Keeps ``current`` when there are too few changes or no clear winner.
    """
    if len(beats) < 2 * beats_per_bar:
        return current
    times = np.asarray(beats)
    votes = np.zeros(beats_per_bar)
    for seg in segments[1:]:
        if seg["root"] is None:
            continue
        i = int(np.argmin(np.abs(times - seg["start"])))
        if abs(times[i] - seg["start"]) < 0.15:
            votes[i % beats_per_bar] += 1
    if votes.sum() < 8:
        return current
    phase = int(votes.argmax())
    current_phase = int(np.argmin(np.abs(times - current[0]))) % beats_per_bar if current else -1
    # Move only when the chords clearly prefer another phase.
    if phase != current_phase and votes[phase] >= 0.4 * votes.sum() and votes[phase] >= 1.5 * votes[current_phase]:
        return [round(float(t), 3) for t in times[phase::beats_per_bar]]
    return current


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
