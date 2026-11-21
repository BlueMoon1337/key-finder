"""Neural stem separation with Demucs (Hybrid Transformer Demucs, Meta AI; MIT licence).

Runs in the engine's own process through Demucs' Python API, so it works in the
frozen desktop engine too. The models' weights are downloaded from the
Hugging Face hub the first time they're needed (or ahead of time from Profile)
and kept in the models folder, so later separations work offline.

Inference runs on Apple's GPU (MPS) on Apple silicon Macs, on an NVIDIA GPU
when PyTorch has CUDA, and on the CPU otherwise.
"""

from __future__ import annotations

import importlib.util
import math
import os
import threading
from collections.abc import Callable
from pathlib import Path

import numpy as np

# Operations MPS doesn't implement fall back to the CPU instead of failing.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

SR = 44100
#: The model each separation mode uses. KEYFINDER_DEMUCS_MODEL overrides it for 2 and 4 stems
#: (e.g. ``htdemucs_ft``: a little better, four times slower).
MODEL_FOR_MODE = {"2stems": "htdemucs", "4stems": "htdemucs", "6stems": "htdemucs_6s"}
MODELS = ("htdemucs", "htdemucs_6s", "htdemucs_ft")
OVERLAP = 0.25

_models_dir: Path | None = None
_cache: dict[str, object] = {}
_lock = threading.Lock()
_download = {"model": None, "error": None}


class Cancelled(Exception):
    """Raised from the progress callback to stop a separation (the song was deleted)."""


class ModelUnavailable(RuntimeError):
    """The weights aren't on this computer and couldn't be downloaded."""


def available() -> bool:
    return importlib.util.find_spec("torch") is not None and importlib.util.find_spec("demucs") is not None


def configure(models_dir: Path) -> None:
    """Keep downloaded weights in ``models_dir`` (unless HF_HOME already says where).

    Must run before huggingface_hub is first imported, which reads HF_HOME once.
    """
    global _models_dir
    _models_dir = Path(models_dir)
    _models_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(_models_dir / "huggingface"))
    # Plain HTTPS downloads from the hub's CDN rather than its Xet client: the files are small
    # enough not to need it, and when the network is blocked Xet retries for minutes before failing.
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")


def model_for(mode: str) -> str:
    override = os.environ.get("KEYFINDER_DEMUCS_MODEL")
    if override and mode != "6stems":
        return override
    return MODEL_FOR_MODE[mode]


def _marker(name: str) -> Path | None:
    return _models_dir / f"{name}.ready" if _models_dir else None


def is_downloaded(name: str) -> bool:
    marker = _marker(name)
    return bool(marker and marker.exists()) or name in _cache


def device() -> str:
    """Where inference runs: KEYFINDER_DEVICE, else cuda, mps or cpu."""
    if os.environ.get("KEYFINDER_DEVICE"):
        return os.environ["KEYFINDER_DEVICE"]
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def status() -> dict:
    """For /api/capabilities: whether Demucs is installed, where it runs and which models are here."""
    if not available():
        return {"installed": False}
    return {
        "installed": True,
        "device": device(),
        "models": {name: is_downloaded(name) for name in MODELS},
        "downloading": _download["model"],
        "download_error": _download["error"],
    }


def load(name: str, on_download: Callable[[], None] | None = None):
    """The model ``name``, downloading its weights first if needed (once per computer)."""
    with _lock:
        if name in _cache:
            return _cache[name]
        if on_download and not is_downloaded(name):
            on_download()
        try:
            model = _fetch(name)
        except Exception as exc:  # network errors, a hub outage, a missing model
            raise ModelUnavailable(
                f"Couldn’t download the Demucs model “{name}” from Hugging Face. Connect to the internet and "
                f"try again; it’s downloaded only once. ({type(exc).__name__}: {str(exc)[:200]})"
            ) from exc
        model.to(device())
        model.eval()
        _cache[name] = model
        marker = _marker(name)
        if marker:
            marker.write_text("ok\n")
        return model


def _fetch(name: str):
    """Load from the Hugging Face hub, where Demucs' models live now; Meta's old server is the fallback.

    If both fail, the hub's error is the one worth reporting.
    """
    from demucs.pretrained import get_model

    if name == "demucs_unittest":  # Demucs' built-in test model: nothing to download
        return get_model(name)
    from demucs.hf import get_hf_model

    try:
        return get_hf_model(name)
    except Exception as hub_error:
        try:
            from demucs.pretrained import REMOTE_ROOT, AnyModelRepo, BagOnlyRepo, RemoteRepo, _parse_remote_files

            remote = RemoteRepo(_parse_remote_files(REMOTE_ROOT / "files.txt"))
            return AnyModelRepo(remote, BagOnlyRepo(REMOTE_ROOT, remote)).get_model(name)
        except Exception:
            raise hub_error from None


def download(name: str) -> None:
    """Fetch a model's weights ahead of time; progress and errors show in :func:`status`."""
    if name not in MODELS:
        raise ValueError(f"unknown Demucs model {name!r}")
    if _download["model"]:
        return
    _download.update(model=name, error=None)

    def run():
        try:
            load(name)
        except Exception as exc:  # noqa: BLE001 - reported through status()
            _download["error"] = str(exc)
        finally:
            _download["model"] = None

    threading.Thread(target=run, name=f"download-{name}", daemon=True).start()


def separate(
    y: np.ndarray,
    mode: str,
    progress: Callable[[float], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    on_download: Callable[[], None] | None = None,
    model_name: str | None = None,
) -> dict[str, np.ndarray]:
    """Split a ``(2, n)`` signal at 44.1 kHz into the stems of ``mode`` (with ``model_name``, if given)."""
    import torch
    from demucs.apply import BagOfModels, apply_model

    model = load(model_name or model_for(mode), on_download)
    wav = torch.from_numpy(np.ascontiguousarray(np.atleast_2d(y), dtype=np.float32))
    if wav.shape[0] == 1:
        wav = wav.repeat(2, 1)
    # Demucs works on a normalised signal (as its own command line does).
    ref = wav.mean(0)
    mean, std = ref.mean(), ref.std() + 1e-8
    wav = (wav - mean) / std

    models = model.models if isinstance(model, BagOfModels) else [model]
    segment = float(models[0].segment)
    stride = int((1 - OVERLAP) * int(SR * segment))
    total = len(models) * max(1, math.ceil(wav.shape[1] / stride))
    done = 0

    def callback(info: dict) -> None:
        nonlocal done
        if info.get("state") != "end":
            return
        done += 1
        if progress:
            progress(min(1.0, done / total))
        if should_stop and should_stop():
            raise Cancelled()

    with torch.no_grad():
        out = apply_model(model, wav[None], device=device(), shifts=1, split=True, overlap=OVERLAP,
                          progress=False, num_workers=0, callback=callback)[0]
    out = (out * std + mean).cpu().numpy().astype(np.float32)
    sources = dict(zip(model.sources, out, strict=True))
    if mode == "2stems":
        vocals = sources.pop("vocals")
        return {"vocals": vocals, "accompaniment": np.sum(list(sources.values()), axis=0)}
    if mode == "6stems":
        return {name: sources[name] for name in ("vocals", "drums", "bass", "guitar", "piano", "other")}
    return {name: sources[name] for name in ("vocals", "drums", "bass", "other")}
