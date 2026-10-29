import itertools

import numpy as np
import pytest
from synth import SR, progression

from keyfinder import chords
from keyfinder.analysis import analyze_signal


def labels(segments):
    return [s["label"] for s in segments if s["root"] is not None]


@pytest.mark.parametrize("prog,bpm,expected", [
    ([(0, "maj"), (7, "maj"), (9, "min"), (5, "maj")], 120, ["C", "G", "Am", "F"]),
    ([(3, "maj"), (0, "min"), (5, "min"), (10, "maj")], 84, ["Eb", "Cm", "Fm", "Bb"]),
    ([(11, "min"), (7, "maj"), (2, "maj"), (9, "maj")], 150, ["Bm", "G", "D", "A"]),
])
def test_basic_chords(prog, bpm, expected):
    result = analyze_signal(progression(prog, bpm=bpm, repeats=3), SR)
    assert labels(result["chords"]["basic"]) == expected * 3


def test_sevenths_in_advanced_mode():
    prog = [(7, "min"), (3, "maj"), (10, "maj"), (2, "7")]
    result = analyze_signal(progression(prog, bpm=105, repeats=3), SR)
    assert labels(result["chords"]["advanced"]) == ["Gm", "Eb", "Bb", "D7"] * 3
    # Basic mode reduces the dominant seventh to its triad.
    assert labels(result["chords"]["basic"]) == ["Gm", "Eb", "Bb", "D"] * 3


def test_segments_cover_track_in_order():
    result = analyze_signal(progression([(0, "maj"), (5, "maj")], repeats=2), SR)
    for level, segs in result["chords"].items():
        assert segs[0]["start"] == 0
        assert all(a["end"] == b["start"] for a, b in itertools.pairwise(segs)), level
        assert segs[-1]["end"] == pytest.approx(result["duration"], abs=0.05)


def test_silence_is_no_chord():
    chroma = np.zeros((12, 200))
    segs = chords.recognize(chroma, chroma, np.arange(0, 200, 20), 43.0)
    assert [s["label"] for s in segs] == ["N"]


def test_chord_label_spelling():
    assert chords.chord_label(10, "min7", flats=True) == "Bbm7"
    assert chords.chord_label(10, "min7", flats=False) == "A#m7"
    assert chords.chord_label(None, None) == "N"
