"""Demucs integration. Uses Demucs' own small, untrained test model ("demucs_unittest"),
so these check the plumbing (shapes, progress, cancellation, fallback, API), not quality,
and need no download."""

import io
import random

import numpy as np
import pytest

pytest.importorskip("demucs")

from fastapi.testclient import TestClient  # noqa: E402
from synth import progression  # noqa: E402

from keyfinder import audio, neural, separation  # noqa: E402
from keyfinder.server import create_app  # noqa: E402

SR = neural.SR


@pytest.fixture(autouse=True)
def unittest_model(monkeypatch, tmp_path):
    monkeypatch.setenv("KEYFINDER_DEMUCS_MODEL", "demucs_unittest")
    monkeypatch.setenv("KEYFINDER_DEVICE", "cpu")
    neural.configure(tmp_path / "models")
    yield
    neural._cache.clear()


def stereo(seconds=3.0):
    t = np.arange(int(seconds * SR)) / SR
    return np.vstack([np.sin(2 * np.pi * 220 * t), np.sin(2 * np.pi * 330 * t)]).astype(np.float32) * 0.3


def test_status_reports_installed_and_device():
    status = neural.status()
    assert status["installed"] is True and status["device"] == "cpu"
    assert set(status["models"]) == {"htdemucs", "htdemucs_6s"}


@pytest.mark.parametrize("mode,names", [
    ("4stems", ["vocals", "drums", "bass", "other"]),
    ("2stems", ["vocals", "accompaniment"]),
])
def test_separate_shapes_and_progress(mode, names):
    y = stereo()
    seen = []
    stems = neural.separate(y, mode, progress=seen.append)
    assert list(stems) == names
    for stem in stems.values():
        assert stem.shape == y.shape and stem.dtype == np.float32 and np.isfinite(stem).all()
    assert seen and seen == sorted(seen) and seen[-1] == pytest.approx(1.0)
    assert neural.is_downloaded("demucs_unittest")


def test_two_stems_accompaniment_is_the_other_three():
    y = stereo()
    # Demucs shifts the input by a random amount (its "shifts" trick); same seed, same shift.
    random.seed(1)
    four = neural.separate(y, "4stems")
    random.seed(1)
    two = neural.separate(y, "2stems")
    np.testing.assert_allclose(two["vocals"], four["vocals"], atol=1e-5)
    np.testing.assert_allclose(two["accompaniment"], four["drums"] + four["bass"] + four["other"], atol=1e-4)


def test_cancel_stops_the_separation():
    with pytest.raises(neural.Cancelled):
        neural.separate(stereo(), "4stems", should_stop=lambda: True)


def test_download_announced_only_the_first_time():
    calls = []
    neural.separate(stereo(1.0), "4stems", on_download=lambda: calls.append(1))
    neural.separate(stereo(1.0), "4stems", on_download=lambda: calls.append(1))
    assert calls == [1]


def test_unknown_model_download_is_refused():
    with pytest.raises(ValueError):
        neural.download("not-a-model")


# ---------------------------------------------------------------- through the job queue


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("KEYFINDER_UI_DIR", str(tmp_path / "no-ui"))
    with TestClient(create_app(tmp_path / "data", inline=True, models_dir=tmp_path / "models")) as c:
        yield c


@pytest.fixture
def song_bytes(tmp_path):
    y = progression([(0, "maj"), (7, "maj")], bpm=120, repeats=1)
    path = tmp_path / "song.wav"
    audio.save(path, np.vstack([y, y]), 22050)
    return path.read_bytes()


def upload(client, data, backend):
    res = client.post("/api/songs", files={"file": ("song.wav", io.BytesIO(data), "audio/wav")},
                      data={"mode": "4stems", "backend": backend})
    assert res.status_code == 201, res.text
    return client.get(f"/api/songs/{res.json()['id']}").json()


def test_job_uses_demucs_when_available(client, song_bytes, monkeypatch):
    assert client.get("/api/capabilities").json()["demucs"]["installed"] is True
    from keyfinder import jobs

    stages = []
    real_update = jobs.JobStore._update

    def spy(self, song_id, **fields):
        if "stage" in fields:
            stages.append(fields["stage"])
        return real_update(self, song_id, **fields)

    monkeypatch.setattr(jobs.JobStore, "_update", spy)
    song = upload(client, song_bytes, "auto")
    # The first time, the model "downloads", then the stage goes back to separating.
    i = stages.index("Downloading the Demucs model (first time only)")
    assert stages[i + 1] == "Separating stems with Demucs"
    assert song["status"] == "ready", song["error"]
    assert song["backend"] == "demucs" and song["warning"] is None
    assert song["stems"] == ["original", "vocals", "drums", "bass", "other"]


def test_offline_first_run_falls_back_to_fast_separator(client, song_bytes, monkeypatch):
    def offline(*_args, **_kwargs):
        raise neural.ModelUnavailable("Couldn’t download the Demucs model.")

    monkeypatch.setattr(neural, "load", offline)
    song = upload(client, song_bytes, "auto")
    assert song["status"] == "ready" and song["backend"] == "dsp"
    assert "fast separator" in song["warning"]
    # Asking for Demucs specifically fails instead of quietly using something else.
    song = upload(client, song_bytes, "demucs")
    assert song["status"] == "error" and "Demucs model" in song["error"]


def test_download_endpoint(client):
    assert client.post("/api/demucs/download", json={"model": "nope"}).status_code == 400


def test_backend_choice_prefers_demucs():
    assert separation.choose_backend("auto", "6stems") == "demucs"
    assert "demucs" in separation.available_backends()


def test_hub_error_is_reported_when_both_sources_fail(monkeypatch):
    import demucs.hf
    import demucs.repo

    def hub_down(name):
        raise ConnectionError("hub unreachable")

    def legacy_down(self, sig):
        raise OSError("legacy server unreachable")

    monkeypatch.setenv("KEYFINDER_DEMUCS_MODEL", "htdemucs")
    monkeypatch.setattr(demucs.hf, "get_hf_model", hub_down)
    monkeypatch.setattr(demucs.repo.RemoteRepo, "get_model", legacy_down)
    with pytest.raises(neural.ModelUnavailable, match="hub unreachable"):
        neural.load("htdemucs")
    assert not neural.is_downloaded("htdemucs")


def test_xet_client_is_off():
    import os

    assert os.environ.get("HF_HUB_DISABLE_XET") == "1"
