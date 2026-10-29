import numpy as np
import pytest

from keyfinder import separation

SR = 44100


def stereo_mix(seconds=4.0):
    t = np.arange(int(seconds * SR)) / SR
    rng = np.random.default_rng(1)
    voice = 0.3 * np.sin(2 * np.pi * 440 * t) * (1 + 0.3 * np.sin(2 * np.pi * 5 * t))
    bass = 0.4 * np.sin(2 * np.pi * 55 * t)
    kick = np.zeros_like(t)
    for s in range(0, t.size - 2000, SR // 2):
        kick[s:s + 2000] += rng.standard_normal(2000) * np.exp(-np.arange(2000) / 300) * 0.6
    guitar = 0.2 * np.sin(2 * np.pi * 659 * t)
    mix = np.vstack([voice + bass + kick + guitar, voice + bass + kick]).astype(np.float32)
    return mix, {"vocals": voice, "bass": bass, "drums": kick, "other": guitar / 2}


@pytest.mark.parametrize("mode", separation.DSP_MODES)
def test_stems_sum_to_mix(mode):
    mix, _ = stereo_mix()
    stems = separation.separate_dsp(mix, SR, mode)
    assert list(stems) == list(separation.MODES[mode])
    total = sum(stems.values())
    assert total.shape == mix.shape
    assert np.max(np.abs(total - mix)) < 1e-4


def test_each_source_lands_in_its_stem():
    mix, sources = stereo_mix()
    stems = separation.separate_dsp(mix, SR, "4stems")
    def corr(stem, ref):
        s = stem.mean(axis=0)
        return np.dot(s, ref) / (np.linalg.norm(s) * np.linalg.norm(ref) + 1e-9)

    for name, ref in sources.items():
        assert max(stems, key=lambda k, ref=ref: corr(stems[k], ref)) == name


def test_blocks_join_seamlessly(monkeypatch):
    monkeypatch.setattr(separation, "BLOCK_SECONDS", 1.0)
    monkeypatch.setattr(separation, "PAD_SECONDS", 0.5)
    mix, _ = stereo_mix(3.3)
    stems = separation.separate_dsp(mix, SR, "4stems")
    assert np.max(np.abs(sum(stems.values()) - mix)) < 1e-4


def test_backend_selection():
    assert separation.choose_backend("dsp", "4stems") == "dsp"
    with pytest.raises(ValueError):
        separation.choose_backend("dsp", "6stems")
    with pytest.raises(ValueError):
        separation.choose_backend("nope", "4stems")
    if not separation.demucs_available():
        assert separation.choose_backend("auto") == "dsp"
        with pytest.raises(ValueError):
            separation.choose_backend("demucs")
