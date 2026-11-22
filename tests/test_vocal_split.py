"""Choir isolation (vocal_split.py) and strings & pads (separation.split_strings), without the
downloaded model: a stand-in runs in its place, and synthetic voices stand in for singers."""

import hashlib

import numpy as np
import pytest

from keyfinder import analysis, separation, vocal_split

SR = 44100
rng = np.random.default_rng(7)


def voice(f0: float, seconds: float, detune_cents: float = 0.0, vibrato: float = 0.0, seed: int = 0) -> np.ndarray:
    """A sung-vowel-like tone: harmonics with falling level, optional detune and vibrato."""
    r = np.random.default_rng(seed)
    t = np.arange(int(seconds * SR)) / SR
    f = f0 * 2 ** (detune_cents / 1200)
    phase_mod = vibrato / (2 * np.pi * 5.5) * np.sin(2 * np.pi * 5.5 * t + r.uniform(0, 6))
    return sum(0.3 / h * np.sin(2 * np.pi * h * (f * t + phase_mod) + r.uniform(0, 6)) for h in range(1, 9))


def choir(f0: float, seconds: float, voices: int = 10) -> np.ndarray:
    """Many voices on one note, none exactly in tune with the others: spread evenly over +-45 cents
    (a standard deviation of 29), like the children's choir the clean-up was tuned on, whose
    aperiodicity measured 0.044-0.061 (this one 0.048). Tightly tuned choirs (+-15 cents) read as one
    voice, so the model's own split stands for them."""
    return sum(voice(f0, seconds, c, vibrato=5, seed=i) for i, c in enumerate(np.linspace(-45, 45, voices))) / voices


def stereo(x: np.ndarray) -> np.ndarray:
    return np.vstack([x, x]).astype(np.float32)


# ------------------------------------------------------------------ the model's frame


def test_lead_and_choir_sum_to_the_vocals_and_the_spectrogram_round_trip_is_exact():
    vocals = stereo(voice(330, 12.0, vibrato=6))
    stems, _ = vocal_split.split(vocals, run=lambda spec: spec)  # a "model" that returns its input
    assert np.allclose(stems["lead"] + stems["choir"], vocals, atol=1e-5)
    # Its output is the input again, times the model's level compensation (away from the ends).
    mid = slice(SR, 10 * SR)
    backing = vocal_split._backing(vocals, lambda spec: spec)
    assert np.allclose(backing[:, mid], vocals[:, mid] * vocal_split.COMPENSATE, atol=1e-3)


def test_progress_and_cancel():
    seen = []
    vocal_split.split(stereo(voice(330, 8.0)), progress=seen.append, run=lambda spec: spec * 0)
    assert seen and seen[-1] == 1.0 and seen == sorted(seen)
    with pytest.raises(vocal_split.Cancelled):
        vocal_split.split(stereo(voice(330, 8.0)), should_stop=lambda: True, run=lambda spec: spec * 0)


# ------------------------------------------------------------------ the clean-up


def test_one_voice_is_one_voice_and_many_are_a_choir():
    solo = stereo(voice(330, 10.0, vibrato=6))
    group = stereo(choir(330, 10.0))
    assert not vocal_split.ensemble_mask(solo, solo).any()
    assert vocal_split.ensemble_mask(group, group).mean() > 0.6


def test_a_choir_the_model_calls_the_lead_goes_to_the_choir():
    """Karaoke models call a choir singing the melody alone the lead; the clean-up moves it."""
    group = stereo(choir(330, 12.0))
    stems, notes = vocal_split.split(group, run=lambda spec: spec * 0)  # the model gives it all to the lead
    e = lambda x: float(np.sum(x[:, 2 * SR:10 * SR] ** 2))  # noqa: E731
    assert e(stems["choir"]) > 0.9 * e(group)
    assert notes["choir_led_seconds"] >= 6


def test_a_soloist_stays_the_lead():
    solo = stereo(voice(294, 12.0, vibrato=6))
    stems, notes = vocal_split.split(solo, run=lambda spec: spec * 0)
    assert np.allclose(stems["lead"], solo, atol=1e-6) and notes["choir_led_seconds"] == 0


def test_a_short_blur_isnt_moved():
    """Under two seconds of ensemble-like sound (a breath, a slide) stays where the model put it."""
    x = np.concatenate([voice(294, 5.0, vibrato=6), choir(294, 1.0), voice(294, 5.0, vibrato=6)])
    assert not vocal_split.ensemble_mask(stereo(x), stereo(x)).any()


# ------------------------------------------------------------------ the download


def test_download_keeps_only_the_right_file(tmp_path, monkeypatch):
    payload = b"model weights" * 1000
    src = tmp_path / "model.onnx"
    src.write_bytes(payload)
    vocal_split.configure(tmp_path / "models")
    monkeypatch.setitem(vocal_split.MODEL, "url", src.as_uri())
    monkeypatch.setitem(vocal_split.MODEL, "size", len(payload))
    monkeypatch.setitem(vocal_split.MODEL, "sha256", "0" * 64)
    with pytest.raises(vocal_split.ModelUnavailable):
        vocal_split.ensure()
    assert not vocal_split.is_downloaded() and not list((tmp_path / "models" / "karaoke").iterdir())
    monkeypatch.setitem(vocal_split.MODEL, "sha256", hashlib.sha256(payload).hexdigest())
    called = []
    vocal_split.ensure(on_download=lambda: called.append(1))
    assert vocal_split.is_downloaded() and called == [1]
    vocal_split.ensure(on_download=lambda: called.append(2))  # already here: not again
    assert called == [1]
    status = vocal_split.status()
    assert status["downloaded"] is True and status["model"] == "UVR-MDX-NET Karaoke 2"


# ------------------------------------------------------------------ strings & pads


def test_strings_keep_held_notes_and_leave_short_ones():
    t = np.arange(8 * SR) / SR
    held = voice(440, 8.0, vibrato=8) * (t > 1) * (t < 7)
    plucks = np.zeros_like(t)
    for start in np.arange(0, 8, 0.25):
        i, m = int(start * SR), int(0.12 * SR)
        plucks[i:i + m] += 0.3 * np.sin(2 * np.pi * 660 * t[:m]) * np.exp(-t[:m] * 40)
    e = lambda x: float(np.sum(np.asarray(x, np.float64) ** 2))  # noqa: E731
    s, rest = separation.split_strings(stereo(held), SR)
    assert e(s) > 0.9 * e(stereo(held))
    s, rest = separation.split_strings(stereo(plucks), SR)
    assert e(s) < 0.05 * e(stereo(plucks))
    both = stereo(held + plucks)
    s, rest = separation.split_strings(both, SR)
    assert np.allclose(s + rest, both, atol=1e-5)


# ------------------------------------------------------------------ in a separation


@pytest.mark.parametrize("backend", ["demucs", "best"])
@pytest.mark.parametrize("mode", list(separation.MODES))
@pytest.mark.parametrize("choir_on,strings_on", [(True, False), (False, True), (True, True)])
def test_separation_with_choir_and_strings(monkeypatch, tmp_path, backend, mode, choir_on, strings_on):
    """Demucs or Best quality (stood in for) then the splits: the right stems, summing to the mix."""
    n = 6 * SR
    sources = {name: rng.normal(0, 0.05, (2, n)).astype(np.float32)
               for name in ("vocals", "drums", "bass", "guitar", "piano", "other")}
    mix = sum(sources.values())

    def fake_demucs(y, m, progress=None, *args):
        if progress:
            progress(1.0)
        if m == "6stems":
            return dict(sources)
        if m == "4stems":
            return {"vocals": sources["vocals"], "drums": sources["drums"], "bass": sources["bass"],
                    "other": sources["guitar"] + sources["piano"] + sources["other"]}
        return {"vocals": sources["vocals"], "accompaniment": mix - sources["vocals"]}

    def fake_split(vocals, progress=None, *args, **kwargs):
        if progress:
            progress(1.0)
        return {"lead": vocals * 0.25, "choir": vocals * 0.75}, {"choir_led_seconds": 1.0}

    monkeypatch.setattr(separation.neural, "separate", fake_demucs)
    monkeypatch.setattr(separation, "separate_best", lambda y, m, p=None, *args: fake_demucs(y, m, p))
    monkeypatch.setattr(separation.neural, "available", lambda: True)
    monkeypatch.setattr(separation.vocal_split, "split", fake_split)
    monkeypatch.setattr(separation.vocal_split, "available", lambda: True)
    monkeypatch.setattr(separation.audio, "load", lambda *a, **k: mix)
    notes = {}
    progress = []
    stems, sr = separation.separate(tmp_path / "song.wav", mode, backend, progress.append,
                                    choir=choir_on, strings=strings_on, notes=notes)
    assert tuple(stems) == separation.stem_names(mode, choir_on, strings_on)
    assert np.allclose(sum(stems.values()), mix, atol=1e-4)
    assert ("strings" in stems) == strings_on and ("choir" in stems) == choir_on
    assert progress and progress == sorted(progress) and progress[-1] <= 1.0
    assert (notes == {"choir_led_seconds": 1.0}) == choir_on


def test_choir_and_strings_need_demucs():
    with pytest.raises(ValueError, match="Demucs"):
        separation.check_extras("dsp", True, False)
    with pytest.raises(ValueError, match="Demucs"):
        separation.check_extras("dsp", False, True)
    separation.check_extras("dsp", False, False)


def test_chords_ignore_the_voices_and_two_stem_separations():
    n = SR
    tone = np.ones((2, n), np.float32)
    assert analysis.harmonic_signal({"lead": tone, "choir": tone, "drums": tone}, SR) is None
    assert analysis.harmonic_signal({"vocals": tone, "strings": tone, "accompaniment": tone}, SR) is None
    assert analysis.harmonic_signal({"lead": tone, "choir": tone, "bass": tone, "strings": tone}, SR) is not None


def test_songs_ask_for_choir_and_strings_only_with_demucs(tmp_path):
    from fastapi.testclient import TestClient

    from keyfinder.jobs import JobStore
    from keyfinder.server import create_app

    with pytest.raises(ValueError, match="Demucs"):
        JobStore.check_options("4stems", "dsp", choir=True)
    assert JobStore.check_options("none", "auto", choir=True, strings=True) is None
    with TestClient(create_app(tmp_path / "data", inline=True)) as c:
        caps = c.get("/api/capabilities").json()
        assert caps["choir"]["model"] == "UVR-MDX-NET Karaoke 2" and caps["choir"]["downloaded"] is False
        res = c.post("/api/songs", files={"file": ("a.wav", b"RIFF0000WAVE", "audio/wav")},
                     data={"mode": "4stems", "backend": "dsp", "choir": "true"})
        assert res.status_code == 400 and "Demucs" in res.json()["detail"]
