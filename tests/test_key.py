import numpy as np
import pytest
from synth import SR, progression

from keyfinder import features, key
from keyfinder.analysis import analyze_signal


@pytest.mark.parametrize("tonic,mode,expected", [
    (0, "major", "8B"), (9, "minor", "8A"), (7, "major", "9B"), (4, "minor", "9A"),
    (6, "major", "2B"), (3, "minor", "2A"), (5, "major", "7B"), (2, "minor", "7A"), (4, "major", "12B"),
])
def test_camelot(tonic, mode, expected):
    assert key.camelot(tonic, mode) == expected


def test_relative_key():
    assert key.relative_key(0, "major") == (9, "minor")
    assert key.relative_key(9, "minor") == (0, "major")


def test_profiles_pick_their_own_key():
    for tonic in range(12):
        major = np.roll(key.KRUMHANSL_MAJOR, tonic)[:, None].repeat(4, axis=1)
        minor = np.roll(key.KRUMHANSL_MINOR, tonic)[:, None].repeat(4, axis=1)
        assert (key.detect_key(major)["tonic"], key.detect_key(major)["mode"]) == (tonic, "major")
        assert (key.detect_key(minor)["tonic"], key.detect_key(minor)["mode"]) == (tonic, "minor")


@pytest.mark.parametrize("chords,expected", [
    ([(0, "maj"), (7, "maj"), (9, "min"), (5, "maj")], "C major"),
    ([(9, "min"), (2, "min"), (4, "min"), (9, "min")], "A minor"),
    ([(6, "maj"), (11, "maj"), (1, "7"), (6, "maj")], "F# major"),
    ([(3, "maj"), (0, "min"), (5, "min"), (10, "7")], "Eb major"),
    ([(7, "min"), (3, "maj"), (10, "maj"), (2, "7")], "G minor"),
    ([(11, "min"), (7, "maj"), (2, "maj"), (9, "maj")], "B minor"),
])
def test_detect_key_on_progressions(chords, expected):
    assert analyze_signal(progression(chords, repeats=3), SR)["key"]["name"] == expected


def test_tuning_offset_is_detected():
    # A progression rendered 30 cents sharp should report the offset and still find the key.
    from synth import tone
    chords = [(0, 4, 7), (5, 9, 12), (7, 11, 14)] * 3
    y = np.concatenate([sum(tone(60 + i + 0.3, 1.0) for i in chord) for chord in chords])
    pitch = features.pitch_features(y, SR)
    assert pitch["tuning"] == pytest.approx(0.3, abs=0.06)
    assert key.detect_key(pitch["chroma"])["name"] == "C major"


def test_real_songs_whose_chords_overrule_the_profile():
    # Profiles and chord timelines captured from two recordings (tests/data). Their pitch
    # profiles alone point to A minor and F minor; the chords sit on Dm and Eb.
    import json
    from pathlib import Path

    cases = json.loads((Path(__file__).parent / "data" / "key_from_chords.json").read_text(encoding="utf-8"))
    for name, case in cases.items():
        profile = np.asarray(case["profile"])
        k = key.detect_key(np.tile(profile[:, None], (1, 4)))
        assert k["name"] == case["profile_key"], name
        assert key.refine_with_chords(k, case["chords"])["name"] == case["expected"], name
