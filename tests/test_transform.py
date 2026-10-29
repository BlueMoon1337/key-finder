import numpy as np
import pytest

from keyfinder import audio, transform

SR = audio.SEPARATION_SR


def dominant_freq(y, sr):
    spec = np.abs(np.fft.rfft(y * np.hanning(y.size)))
    return np.fft.rfftfreq(y.size, 1 / sr)[np.argmax(spec)]


@pytest.fixture
def a440(tmp_path):
    t = np.arange(SR * 2) / SR
    path = tmp_path / "a440.wav"
    audio.save(path, 0.5 * np.sin(2 * np.pi * 440 * t), SR)
    return path


@pytest.mark.parametrize("semitones", [-5, 3, 12])
def test_pitch_shift_keeps_duration(a440, tmp_path, semitones):
    out = transform.render(a440, tmp_path / "shifted.wav", semitones=semitones)
    y = audio.load(out, SR)
    assert y.size / SR == pytest.approx(2.0, abs=0.08)
    mid = y[SR // 2: SR + SR // 2]
    assert dominant_freq(mid, SR) == pytest.approx(440 * 2 ** (semitones / 12), rel=0.02)


def test_speed_changes_duration_not_pitch(a440, tmp_path):
    out = transform.render(a440, tmp_path / "slow.wav", speed=0.5)
    y = audio.load(out, SR)
    assert y.size / SR == pytest.approx(4.0, abs=0.1)
    assert dominant_freq(y[SR: 3 * SR], SR) == pytest.approx(440, rel=0.02)


def test_filter_chain():
    assert transform._atempo_chain(0.2)[:2] == [("atempo", "0.5"), ("atempo", "0.5")]
    with pytest.raises(ValueError):
        transform.pitch_tempo_filters(13)
    assert transform.pitch_tempo_filters(0, 1.0) == []


def test_pyav_path_without_rubberband(monkeypatch, a440, tmp_path):
    monkeypatch.setattr(transform, "rubberband_ffmpeg", lambda: None)
    out = transform.render(a440, tmp_path / "up.wav", semitones=2)
    y = audio.load(out, SR)
    assert dominant_freq(y[SR // 2: SR + SR // 2], SR) == pytest.approx(440 * 2 ** (2 / 12), rel=0.02)


def test_mixdown_respects_volumes(tmp_path):
    t = np.arange(SR) / SR
    low, high = tmp_path / "low.wav", tmp_path / "high.wav"
    audio.save(low, 0.4 * np.sin(2 * np.pi * 220 * t), SR)
    audio.save(high, 0.4 * np.sin(2 * np.pi * 1760 * t), SR)
    out = transform.mixdown({"low": low, "high": high}, {"low": 0.0, "high": 1.0}, tmp_path / "mix.wav")
    y = audio.load(out, SR)
    assert dominant_freq(y, SR) == pytest.approx(1760, rel=0.01)
    with pytest.raises(ValueError):
        transform.mixdown({"low": low}, {"low": 0.0}, tmp_path / "none.wav")
