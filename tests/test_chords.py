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


def test_chords_survive_a_sustained_tonic_pad():
    # A pad holding the tonic under the whole song (common in worship sets) used to outvote the chords.
    from synth import tone

    y = progression([(0, "maj"), (5, "maj"), (7, "maj"), (9, "min")], bpm=110, repeats=3)
    pad = np.zeros_like(y)
    for start in range(0, y.size, SR):
        note = 0.5 * (tone(48, 1.0, harmonics=3) + tone(60, 1.0, harmonics=3))
        pad[start:start + note.size] += note[: pad.size - start]
    mixed = (y + pad) / np.abs(y + pad).max()
    result = analyze_signal(mixed, SR)
    # The pad rings on after the progression, so a final C is right too.
    assert labels(result["chords"]["basic"])[:12] == ["C", "F", "G", "Am"] * 3


def test_chords_from_stems_ignore_drums_and_melody():
    from synth import click, tone

    from keyfinder.analysis import chords_from_stems

    harmonic = progression([(2, "maj"), (7, "maj"), (9, "maj"), (2, "maj")], bpm=96, drums=False, repeats=2)
    rng = np.random.default_rng(3)
    drums = np.zeros_like(harmonic)
    k = click()
    for i in range(0, drums.size - k.size, SR // 4):
        drums[i:i + k.size] += 2.0 * k
    drums += 0.05 * rng.standard_normal(drums.size)
    melody = np.concatenate([tone(m, 0.3) for m in [73, 76, 78, 80, 81, 83] * 40])[: harmonic.size]
    melody = np.pad(melody, (0, harmonic.size - melody.size))
    mix = harmonic + drums + melody
    result = analyze_signal(mix, SR)
    stems = {"vocals": melody, "drums": drums, "bass": 0.5 * harmonic, "other": 0.5 * harmonic}
    better = chords_from_stems(result, stems, SR)
    assert labels(better["basic"]) == ["D", "G", "A", "D", "G", "A", "D"]  # the two Ds at the loop join merge
    assert chords_from_stems(result, {"vocals": melody, "accompaniment": harmonic}, SR) is None
