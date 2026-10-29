import numpy as np
import pytest
from synth import SR, click, progression

from keyfinder import features, tempo


def click_track(bpm: float, seconds: float = 20.0) -> np.ndarray:
    y = np.zeros(int(seconds * SR), dtype=np.float32)
    k = click()
    for i, t in enumerate(np.arange(0.5, seconds - 0.1, 60.0 / bpm)):
        s = int(t * SR)
        y[s:s + k.size] += (1.0 if i % 4 == 0 else 0.6) * k[: y.size - s]
    return y


@pytest.mark.parametrize("bpm", [72, 90, 100, 120, 128, 140])
def test_click_track_tempo(bpm):
    y = click_track(bpm)
    fps = SR / features.HOP
    result = tempo.analyze_rhythm(features.onset_strength(y, SR), features.onset_strength(y, SR, max_freq=200), fps)
    assert result["bpm"] == pytest.approx(bpm, rel=0.02)
    # Beats land on the clicks (within ~2 analysis frames).
    expected = np.arange(0.5, 19.9, 60.0 / bpm)
    errors = [np.min(np.abs(expected - b)) for b in result["beats"]]
    assert np.median(errors) < 0.05


@pytest.mark.parametrize("bpm", [84, 105, 120])
def test_music_tempo(bpm):
    y = progression([(0, "maj"), (5, "maj"), (7, "maj"), (0, "maj")], bpm=bpm, repeats=3)
    fps = SR / features.HOP
    result = tempo.analyze_rhythm(features.onset_strength(y, SR), features.onset_strength(y, SR, max_freq=200), fps)
    assert result["bpm"] == pytest.approx(bpm, rel=0.02)


def test_silence_does_not_crash():
    y = np.zeros(SR * 3, dtype=np.float32)
    fps = SR / features.HOP
    result = tempo.analyze_rhythm(features.onset_strength(y, SR), features.onset_strength(y, SR, max_freq=200), fps)
    assert result["beats"] == []


def test_downbeats_follow_chord_changes():
    from keyfinder.analysis import downbeats_from_chords

    beats = [round(0.5 * i, 3) for i in range(40)]
    # Chords change on every 4th beat starting at beat index 3; the first guess said index 0.
    segments = [{"start": 0.0, "root": 0}] + [{"start": beats[i], "root": i % 12} for i in range(3, 40, 4)]
    assert downbeats_from_chords(beats, segments, beats[0::4]) == beats[3::4]
    # A guess the chords agree with is kept, and so is any guess when the chords are unclear.
    assert downbeats_from_chords(beats, segments, beats[3::4]) == beats[3::4]
    few = segments[:4]
    assert downbeats_from_chords(beats, few, beats[0::4]) == beats[0::4]


def test_misleading_accents_are_corrected_by_chords():
    # Accented hits on beat 2 of each bar while the chords change on beat 1.
    from synth import tone

    from keyfinder.analysis import analyze_signal

    y = progression([(0, "maj"), (5, "maj"), (7, "maj"), (9, "min")], bpm=100, drums=False, repeats=3)
    k = click()
    beat = 60 / 100
    for b in range(48):
        s = int(b * beat * SR)
        if b % 4 == 1:
            low = tone(31, 0.3, harmonics=2) * 2.5
            y[s:s + low.size] += low[: y.size - s]
        y[s:s + k.size] += (1.5 if b % 4 == 1 else 0.3) * k[: y.size - s]
    result = analyze_signal(y / np.abs(y).max(), SR)
    beats = np.array(result["beats"])
    changes = [c["start"] for c in result["chords"]["basic"][1:] if c["root"] is not None]
    on_downbeat = sum(min(abs(np.array(result["downbeats"]) - t)) < 0.15 for t in changes)
    assert on_downbeat >= 0.8 * len(changes), (result["downbeats"][:4], changes[:4], beats[:6])
