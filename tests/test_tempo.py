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
