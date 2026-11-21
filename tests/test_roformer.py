"""Best quality separation (BS-RoFormer vocals, then Demucs). A tiny, untrained BS-RoFormer and
Demucs' own test model stand in for the real ones, so these check the plumbing (shapes, progress,
cancelling, the download and its checksum, the job), not quality, and need no download."""

import hashlib
import io

import numpy as np
import pytest

pytest.importorskip("demucs")
torch = pytest.importorskip("torch")

from fastapi.testclient import TestClient  # noqa: E402
from synth import progression  # noqa: E402

from keyfinder import audio, neural, roformer, separation  # noqa: E402
from keyfinder.server import create_app  # noqa: E402

SR = roformer.SR
TINY = dict(
    dim=16, depth=1, stereo=True, num_stems=1, time_transformer_depth=1, freq_transformer_depth=1,
    freqs_per_bands=(1,) * 8 + (1017,), dim_head=8, heads=2, stft_n_fft=2048, stft_hop_length=441,
    stft_win_length=2048, mask_estimator_depth=2,
)


@pytest.fixture(autouse=True)
def tiny_models(monkeypatch, tmp_path):
    monkeypatch.setenv("KEYFINDER_DEMUCS_MODEL", "demucs_unittest")
    monkeypatch.setenv("KEYFINDER_DEVICE", "cpu")
    neural.configure(tmp_path / "models")
    roformer.configure(tmp_path / "models")
    torch.manual_seed(0)
    tiny = roformer._network()(**TINY).eval()
    announced = []

    def load(on_download=None, should_stop=None):
        if not announced and on_download:
            announced.append(True)
            on_download()
        return tiny

    monkeypatch.setattr(roformer, "load", load)
    # Short windows, so a few seconds of audio take several of them.
    monkeypatch.setattr(roformer, "CHUNK", SR)
    yield
    neural._cache.clear()


def stereo(seconds=3.0):
    t = np.arange(int(seconds * SR)) / SR
    return np.vstack([np.sin(2 * np.pi * 220 * t), np.sin(2 * np.pi * 330 * t)]).astype(np.float32) * 0.3


def test_network_keeps_the_length_and_channels():
    net = roformer._network()(**TINY).eval()
    with torch.no_grad():
        out = net(torch.from_numpy(stereo(1.0))[None])
    assert tuple(out.shape) == (1, 2, SR)


@pytest.mark.parametrize("seconds", [0.4, 2.7])
def test_vocals_cover_the_whole_song_and_report_progress(seconds):
    y = stereo(seconds)
    steps = []
    vocals = roformer.separate_vocals(y, steps.append)
    assert vocals.shape == y.shape and vocals.dtype == np.float32
    assert np.all(np.isfinite(vocals))
    assert steps == sorted(steps) and steps[-1] == pytest.approx(1.0)


def test_cancel_stops_the_vocals():
    with pytest.raises(neural.Cancelled):
        roformer.separate_vocals(stereo(3.0), should_stop=lambda: True)


@pytest.mark.parametrize("mode,names", [("2stems", ["vocals", "accompaniment"]),
                                        ("4stems", ["vocals", "drums", "bass", "other"])])
def test_best_stems_add_up_to_the_mix(mode, names):
    y = stereo(2.0)
    steps = []
    stems = separation.separate_best(y, mode, steps.append)
    assert list(stems) == names
    assert np.max(np.abs(sum(stems.values()) - y)) < 1e-3
    assert steps == sorted(steps) and steps[-1] == pytest.approx(1.0)


def test_backend_choice():
    assert "best" in separation.available_backends()
    assert separation.choose_backend("best", "6stems") == "best"
    # Best quality is chosen, never the automatic choice.
    assert separation.choose_backend("auto", "4stems") == "demucs"


def test_download_is_checked_and_kept(monkeypatch, tmp_path):
    good = b"weights" * 1000
    monkeypatch.setattr(roformer, "MODEL", {**roformer.MODEL, "urls": ("https://a.example/m.ckpt", "https://b.example/m.ckpt"),
                                            "sha256": hashlib.sha256(good).hexdigest(), "size": len(good)})
    served = []

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen(req, timeout=None, context=None):
        served.append(req.full_url)
        # The first place serves a damaged file: it's refused, and the second is tried.
        return Response(b"broken" if "a.example" in req.full_url else good)

    monkeypatch.setattr(roformer.urllib.request, "urlopen", urlopen)
    assert not roformer.is_downloaded()
    path = roformer._fetch()
    assert path.read_bytes() == good and roformer.is_downloaded()
    assert served == ["https://a.example/m.ckpt", "https://b.example/m.ckpt"]
    assert not path.with_suffix(".part").exists()


def test_download_fails_clearly_when_offline(monkeypatch):
    def offline(*_a, **_k):
        raise OSError("no network")

    monkeypatch.setattr(roformer.urllib.request, "urlopen", offline)
    with pytest.raises(neural.ModelUnavailable, match="Best quality"):
        roformer._fetch()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("KEYFINDER_UI_DIR", str(tmp_path / "no-ui"))
    with TestClient(create_app(tmp_path / "data", inline=True, models_dir=tmp_path / "models")) as c:
        yield c


def test_job_separates_with_best_quality(client, tmp_path, monkeypatch):
    caps = client.get("/api/capabilities").json()
    assert "best" in caps["backends"] and caps["best"]["installed"] is True
    y = progression([(0, "maj"), (7, "maj")], bpm=120, repeats=1)
    path = tmp_path / "song.wav"
    audio.save(path, np.vstack([y, y]), 22050)
    from keyfinder import jobs

    stages = []
    real_update = jobs.JobStore._update

    def spy(self, song_id, **fields):
        if "stage" in fields:
            stages.append(fields["stage"])
        return real_update(self, song_id, **fields)

    monkeypatch.setattr(jobs.JobStore, "_update", spy)
    res = client.post("/api/songs", files={"file": ("song.wav", io.BytesIO(path.read_bytes()), "audio/wav")},
                      data={"mode": "4stems", "backend": "best"})
    assert res.status_code == 201, res.text
    song = client.get(f"/api/songs/{res.json()['id']}").json()
    assert song["status"] == "ready", song["error"]
    assert song["backend"] == "best"
    assert song["stems"] == ["original", "vocals", "drums", "bass", "other"]
    assert "Downloading the Best quality models (first time only)" in stages
    assert "Separating stems with Best quality (BS-RoFormer and Demucs)" in stages
