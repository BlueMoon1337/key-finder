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


def test_downbeats_follow_a_phase_shift_between_sections():
    # The tracker lost a beat between sections: chords change on beat index 0 mod 4 for the
    # first half and 2 mod 4 for the second (as in a rubato piano recording).
    from keyfinder.analysis import downbeats_from_chords

    beats = [round(0.8 * i, 3) for i in range(80)]
    changes = list(range(0, 40, 4)) + list(range(42, 80, 4))
    segments = [{"start": 0.0, "root": 0}] + [{"start": beats[i], "root": (i // 4) % 12} for i in changes[1:]]
    downbeats = downbeats_from_chords(beats, segments, beats[0::4])
    assert all(beats[i] in downbeats for i in changes)
    assert beats[40] not in downbeats  # the old phase ends where the new one begins


def test_one_stray_change_does_not_shift_the_bar():
    from keyfinder.analysis import downbeats_from_chords

    beats = [round(0.5 * i, 3) for i in range(80)]
    changes = [i for i in range(0, 80, 4) if i != 40] + [41]
    segments = [{"start": 0.0, "root": 0}] + [{"start": beats[i], "root": i % 12} for i in sorted(changes)[1:]]
    assert downbeats_from_chords(beats, segments, beats[0::4]) == beats[0::4]


# ------------------------------------------------------------------ tempo changes

FPS = SR / features.HOP
CHANGE_CHORDS = [(2, "maj"), (9, "maj"), (11, "min"), (7, "maj")]


def rhythm_of(y):
    return tempo.analyze_rhythm(features.onset_strength(y, SR), features.onset_strength(y, SR, max_freq=200.0), FPS)


@pytest.mark.parametrize("first, second", [(90, 120), (120, 100), (78, 104), (130, 96)])
def test_a_tempo_change_makes_two_sections(first, second):
    a = progression(CHANGE_CHORDS, bpm=first, repeats=6)
    y = np.concatenate([a, progression(CHANGE_CHORDS, bpm=second, repeats=6)])
    cut = a.size / SR
    result = rhythm_of(y)
    sections = result["tempo_sections"]
    assert [s["bpm"] for s in sections] == [pytest.approx(first, rel=0.02), pytest.approx(second, rel=0.02)]
    assert sections[1]["start"] == pytest.approx(cut, abs=4.0)
    assert result["bpm"] == sections[0]["bpm"]  # the song's tempo is its first, as a chart gives it
    beats = np.asarray(result["beats"])
    assert np.mean(np.diff(beats[beats < cut - 4])) == pytest.approx(60 / first, rel=0.02)
    assert np.mean(np.diff(beats[beats > cut + 4])) == pytest.approx(60 / second, rel=0.02)


def test_steady_songs_keep_one_tempo():
    y = progression(CHANGE_CHORDS, bpm=112, repeats=12)
    assert len(rhythm_of(y)["tempo_sections"]) == 1
    # Half time, a small push (6 %): the same tempo, counted differently or played a little faster.
    halftime = np.concatenate([y, progression(CHANGE_CHORDS, bpm=56, repeats=6)])
    assert len(rhythm_of(halftime)["tempo_sections"]) == 1
    pushed = np.concatenate([y, progression(CHANGE_CHORDS, bpm=118.7, repeats=12)])
    assert len(rhythm_of(pushed)["tempo_sections"]) == 1


def test_a_dotted_eighth_delay_is_not_a_new_tempo():
    """A guitar delay on dotted eighths pulses at 4:3 of the tempo; the kick and bass don't."""
    y = progression(CHANGE_CHORDS, bpm=128, repeats=14)
    t = np.arange(int(0.04 * SR)) / SR
    tick = (np.sin(2 * np.pi * 2500 * t) * np.exp(-t / 0.008)).astype(np.float32)
    for p in np.arange(30.0, 75.0, 0.75 * 60 / 128):  # dotted eighths, for 45 seconds
        s = int(p * SR)
        y[s:s + tick.size] += 0.9 * tick[: y.size - s]
    assert len(rhythm_of(y)["tempo_sections"]) == 1


def test_click_track_sections():
    def grid(*parts):
        t, out = 1.0, []
        for bpm, n in parts:
            for _ in range(n):
                out.append(t)
                t += 60 / bpm
        return out

    assert len(tempo.sections_from_beats(grid((90, 120)))) == 1
    assert len(tempo.sections_from_beats(grid((78, 60), (84, 60)))) == 1  # under 10 %: a push, not a change
    sections = tempo.sections_from_beats(grid((90, 60), (120, 80)))
    assert [s["bpm"] for s in sections] == [pytest.approx(90, abs=0.2), pytest.approx(120, abs=0.2)]
    assert sections[1]["start"] == pytest.approx(1 + 60 * 60 / 90, abs=0.7)


def _steps(*parts, jitter=0.0, seed=0):
    """Beat times: (bpm, beats) parts in a row, with optional beat-tracker jitter."""
    times, t = [0.0], 0.0
    for bpm, n in parts:
        for _ in range(n):
            t += 60.0 / bpm
            times.append(t)
    return list(np.asarray(times) + np.random.default_rng(seed).normal(0, jitter, len(times)))


@pytest.mark.parametrize("seed", range(3))
def test_tempo_changes_land_on_the_beat_they_happen(seed):
    beats = _steps((120, 32), (90, 32), (140, 40), jitter=0.01, seed=seed)
    changes = tempo.tempo_changes(beats)
    assert [round(c["bpm"]) for c in changes] == [120, 90, 140]
    assert changes[0]["start"] == 0.0
    assert abs(changes[1]["start"] - 16.0) < 0.03 and abs(changes[2]["start"] - (16 + 32 * 60 / 90)) < 0.03


def test_a_drifting_performance_keeps_one_tempo():
    beats = list(np.cumsum([0.6 * (1 - 0.02 * i / 200) for i in range(200)]))
    assert len(tempo.tempo_changes(beats)) == 1


def test_bars_follow_the_downbeats():
    beats = _steps((120, 40))
    downbeats = [beats[i] for i in (0, 4, 8, 12, 14, 17, 20, 23)]
    assert tempo.meter_changes(beats, downbeats) == [
        {"start": 0.0, "beats": 4},
        {"start": beats[12], "beats": 2},
        {"start": beats[14], "beats": 3},
    ]
    m = tempo.beat_map(beats[3:], downbeats[1:])
    assert m["offset"] == round(beats[4], 3) and m["tempos"] == [{"start": 0.0, "bpm": 120.0}]
