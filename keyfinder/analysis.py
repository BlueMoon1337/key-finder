"""Full-track analysis: key, tempo/beat grid and chords at every detail level."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from . import audio, chords, features, key, tempo


def analyze_signal(y: np.ndarray, sr: int = audio.ANALYSIS_SR) -> dict:
    fps = sr / features.HOP
    pitch = features.pitch_features(y, sr)
    onset = features.onset_strength(y, sr)
    bass_onset = features.onset_strength(y, sr, max_freq=200.0)
    rhythm = tempo.analyze_rhythm(onset, bass_onset, fps)
    beat_frames = np.round(np.asarray(rhythm["beats"]) * fps).astype(int)

    detected = key.detect_key(pitch["chroma"])
    basic = chords.recognize(pitch["chroma"], pitch["bass"], beat_frames, fps, level="basic", key=detected)
    detected = key.refine_with_chords(detected, basic)
    chord_levels = {
        level: chords.recognize(pitch["chroma"], pitch["bass"], beat_frames, fps, level=level, key=detected)
        for level in chords.LEVELS
    }
    return {
        "duration": round(y.size / sr, 3),
        "tuning_cents": round(100.0 * pitch["tuning"], 1),
        "key": detected,
        **rhythm,
        "chords": chord_levels,
        "waveform": audio.waveform_peaks(y),
    }


def analyze_file(path: str | Path) -> dict:
    return analyze_signal(audio.load(path, audio.ANALYSIS_SR), audio.ANALYSIS_SR)
