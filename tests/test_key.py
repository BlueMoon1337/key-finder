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
    ([(11, "min"), (4, "min"), (6, "maj"), (11, "min")], "B minor"),
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
    # Profiles and chord timelines captured from three recordings (tests/data). Their pitch
    # profiles alone point elsewhere; the chords (and, for two, published chord charts) say
    # D minor, Eb major and F minor.
    import json
    from pathlib import Path

    cases = json.loads((Path(__file__).parent / "data" / "key_from_chords.json").read_text(encoding="utf-8"))
    for name, case in cases.items():
        profile = np.asarray(case["profile"])
        k = key.detect_key(np.tile(profile[:, None], (1, 4)))
        assert k["name"] == case["profile_key"], name
        assert key.refine_with_chords(k, case["chords"])["name"] == case["expected"], name


def test_relative_key_ambiguity_gives_one_of_the_pair():
    # Bm - G - D - A is i-VI-III-VII in B minor and vi-IV-I-V in D major: either is a fair reading.
    name = analyze_signal(progression([(11, "min"), (7, "maj"), (2, "maj"), (9, "maj")], repeats=3), SR)["key"]["name"]
    assert name in ("B minor", "D major")


def test_key_change_is_found_and_spelled_per_section():
    # 64 s in C major (I-IV-V-I), then 64 s in Eb major: two sections, chords spelled for each.
    from synth import tone

    beat = 0.5
    y = np.zeros(int(256 * beat * SR + SR), dtype=np.float32)
    for b in range(256):
        tonic = 0 if b < 128 else 3
        root = tonic + (0, 5, 7, 0)[(b // 4) % 4]
        s = int(b * beat * SR)
        note = sum(0.25 * tone(60 + root + i, beat) for i in (0, 4, 7)) + 0.4 * tone(36 + root, beat, harmonics=3)
        y[s:s + note.size] += note
    result = analyze_signal(y / np.abs(y).max(), SR)
    sections = result["key_sections"]
    assert [s["name"] for s in sections] == ["C major", "Eb major"]
    assert abs(sections[1]["start"] - 64) < 8
    late = [c["label"] for c in result["chords"]["basic"] if c["start"] > 72 and c["root"] is not None]
    assert "Ab" in late and "Bb" in late and "G#" not in late and "A#" not in late


def test_one_key_song_has_one_section():
    result = analyze_signal(progression([(0, "maj"), (7, "maj"), (9, "min"), (5, "maj")], bpm=120, repeats=8), SR)
    assert [s["name"] for s in result["key_sections"]] == ["C major"]
    assert result["key_sections"][0]["start"] == 0 and result["key_sections"][0]["end"] == result["duration"]


def test_song_that_changes_key_is_labelled_with_its_first_key():
    from synth import tone

    from keyfinder.analysis import settle_key  # noqa: F401  (the rule lives there)

    beat = 0.5
    y = np.zeros(int(256 * beat * SR + SR), dtype=np.float32)
    for b in range(256):
        tonic = 2 if b < 128 else 4  # D major, then E major
        root = tonic + (0, 5, 7, 0)[(b // 4) % 4]
        s = int(b * beat * SR)
        note = sum(0.25 * tone(60 + root + i, beat) for i in (0, 4, 7)) + 0.4 * tone(36 + root, beat, harmonics=3)
        y[s:s + note.size] += note
    result = analyze_signal(y / np.abs(y).max(), SR)
    assert [s["name"] for s in result["key_sections"]] == ["D major", "E major"]
    assert result["key"]["name"] == "D major"
