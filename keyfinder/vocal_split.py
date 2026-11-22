"""Splitting a vocals stem into the lead singer and the choir.

Two steps:

1. A "karaoke" model, UVR-MDX-NET Karaoke 2 (from the Ultimate Vocal Remover project, distributed
   under the MIT licence), separates the lead voice from backing voices, even where they sing at the
   same moment. Fed the vocals stem Demucs made, its "instrumental" output is the backing voices.
   It runs on onnxruntime, which the engine already has for transcription; the weights (~53 MB)
   are downloaded once, checked against their SHA-256, and kept in the models folder.

2. A clean-up on top. Karaoke models learn from songs with one lead singer, so where a choir
   carries the melody on its own they call it the lead. Many voices on one note never line up
   exactly: even on held notes their sum is less periodic than one voice. So wherever the model's
   "lead" stays like that for a couple of seconds (YIN aperiodicity, measured on steady notes only,
   since speech glides between them), it's moved to the choir. A soloist over a choir keeps a clean
   lead, so the model's split stands there.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import threading
import urllib.request
from collections.abc import Callable
from pathlib import Path

import numpy as np
from scipy import ndimage, signal

SR = 44100

MODEL = {
    "name": "UVR-MDX-NET Karaoke 2",
    "file": "UVR_MDXNET_KARA_2.onnx",
    "url": "https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/UVR_MDXNET_KARA_2.onnx",
    "sha256": "bf32e15105a09c0f7dddd2b67346146334d6f3ecb399ed7638eba2ab07cbf5f4",
    "size": 52786726,
}
# The model's spectrogram settings (UVR's model_data.json for this file).
N_FFT, HOP, DIM_F, DIM_T, COMPENSATE = 5120, 1024, 2048, 256, 1.065
N_BINS = N_FFT // 2 + 1
CHUNK = HOP * (DIM_T - 1)
TRIM = N_FFT // 2
GEN = CHUNK - 2 * TRIM

# The clean-up: aperiodicity on steady notes above this means many voices (measured: one voice,
# sung or spoken, 0.01-0.04; a choir 0.044-0.061).
ENSEMBLE_APERIODICITY = 0.04
MIN_ENSEMBLE_SECONDS = 2.0

_dir: Path | None = None
_session = None
_lock = threading.Lock()
_download = {"active": False, "received": 0, "error": None}


class Cancelled(Exception):
    pass


class ModelUnavailable(RuntimeError):
    pass


def configure(models_dir: Path) -> None:
    global _dir
    _dir = Path(models_dir) / "karaoke"


def available() -> bool:
    """onnxruntime runs the model; torch does its spectrograms exactly as the model was trained with."""
    return importlib.util.find_spec("onnxruntime") is not None and importlib.util.find_spec("torch") is not None


def model_path() -> Path | None:
    return _dir / MODEL["file"] if _dir else None


def is_downloaded() -> bool:
    p = model_path()
    return bool(p and p.exists() and p.stat().st_size == MODEL["size"])


def status() -> dict:
    """For /api/capabilities."""
    return {
        "installed": available(),
        "model": MODEL["name"],
        "downloaded": is_downloaded(),
        "downloading": _download["active"],
        "progress": round(_download["received"] / MODEL["size"], 3) if _download["active"] else None,
        "download_error": _download["error"],
    }


def _fetch() -> None:
    """Download the weights, checking them against the known SHA-256 before keeping them."""
    target = model_path()
    if target is None:
        raise ModelUnavailable("KeyFinder's models folder isn't set up.")
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".part")
    digest = hashlib.sha256()
    _download["received"] = 0
    try:
        with urllib.request.urlopen(MODEL["url"], timeout=60) as res, open(partial, "wb") as out:
            while chunk := res.read(1 << 20):
                out.write(chunk)
                digest.update(chunk)
                _download["received"] += len(chunk)
    except Exception as exc:
        partial.unlink(missing_ok=True)
        raise ModelUnavailable(
            f"Couldn’t download the choir model ({MODEL['name']}). Connect to the internet and try again; it’s "
            f"downloaded only once. ({type(exc).__name__}: {str(exc)[:200]})"
        ) from exc
    if digest.hexdigest() != MODEL["sha256"]:
        partial.unlink(missing_ok=True)
        raise ModelUnavailable(
            "The choir model that downloaded isn’t the expected file, so it wasn’t kept. Try again later."
        )
    os.replace(partial, target)


def ensure(on_download: Callable[[], None] | None = None) -> None:
    """Have the weights on this computer, downloading them the first time."""
    with _lock:
        if is_downloaded():
            return
        if on_download:
            on_download()
        _fetch()


def download() -> None:
    """Fetch the weights ahead of time (Profile); progress and errors show in :func:`status`."""
    if _download["active"] or is_downloaded():
        return
    _download.update(active=True, error=None)

    def run():
        try:
            ensure()
        except Exception as exc:  # noqa: BLE001 - reported through status()
            _download["error"] = str(exc)
        finally:
            _download["active"] = False

    threading.Thread(target=run, name="download-karaoke", daemon=True).start()


def _session_run():
    global _session
    with _lock:
        if _session is None:
            import onnxruntime as ort

            _session = ort.InferenceSession(str(model_path()), providers=["CPUExecutionProvider"])
    return lambda spec: _session.run(None, {"input": spec})[0]


# ------------------------------------------------------------------ the model


def _backing(vocals: np.ndarray, run: Callable[[np.ndarray], np.ndarray], progress=None,
             should_stop=None) -> np.ndarray:
    """The model's backing-voices estimate for a ``(2, n)`` signal at 44.1 kHz (MDX-Net, chunked)."""
    import torch

    window = torch.hann_window(N_FFT, periodic=True)

    def stft(x):  # [B, 2, CHUNK] -> [B, 4, DIM_F, DIM_T]: left re/im, right re/im
        x = torch.stft(x.reshape(-1, CHUNK), N_FFT, HOP, window=window, center=True, return_complex=True)
        x = torch.view_as_real(x).permute(0, 3, 1, 2)
        return x.reshape(-1, 2, 2, N_BINS, DIM_T).reshape(-1, 4, N_BINS, DIM_T)[:, :, :DIM_F]

    def istft(x):
        x = torch.cat([x, torch.zeros(x.shape[0], 4, N_BINS - DIM_F, DIM_T)], -2)
        x = x.reshape(-1, 2, 2, N_BINS, DIM_T).reshape(-1, 2, N_BINS, DIM_T).permute(0, 2, 3, 1).contiguous()
        x = torch.istft(torch.view_as_complex(x), N_FFT, HOP, window=window, center=True)
        return x.reshape(-1, 2, CHUNK)

    n = vocals.shape[1]
    pad = GEN - n % GEN
    padded = np.concatenate([np.zeros((2, TRIM), np.float32), vocals.astype(np.float32),
                             np.zeros((2, pad + TRIM), np.float32)], 1)
    starts = range(0, n + pad, GEN)
    parts = []
    with torch.no_grad():
        for k, i in enumerate(starts):
            spec = stft(torch.from_numpy(np.ascontiguousarray(padded[None, :, i:i + CHUNK]))).numpy()
            out = torch.from_numpy(np.asarray(run(spec), dtype=np.float32))
            parts.append(istft(out)[0, :, TRIM:-TRIM].numpy())
            if progress:
                progress((k + 1) / len(starts))
            if should_stop and should_stop():
                raise Cancelled()
    return np.concatenate(parts, 1)[:, :n] * COMPENSATE


# ------------------------------------------------------------------ the clean-up

A_SR, A_FRAME, A_HOP = 16000, 1024, 160  # analysis: 64 ms frames every 10 ms
LAG_LO, LAG_HI = A_SR // 900, A_SR // 70  # pitches 70-900 Hz


def yin(x: np.ndarray, sr: int = A_SR) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per 10 ms frame of a mono signal at ``sr``: pitch (Hz), YIN aperiodicity (0 = one perfect
    pitch) and level (RMS)."""
    n = 1 + max(0, (len(x) - A_FRAME)) // A_HOP
    f0, ap, rms = np.zeros(n), np.ones(n), np.zeros(n)
    w = A_FRAME // 2
    taus = np.arange(LAG_HI + 1)
    for b in range(0, n, 512):
        idx = np.arange(b, min(n, b + 512))
        frames = np.stack([x[i * A_HOP:i * A_HOP + A_FRAME] for i in idx]).astype(np.float64)
        if frames.shape[1] < A_FRAME:
            frames = np.pad(frames, ((0, 0), (0, A_FRAME - frames.shape[1])))
        frames -= frames.mean(axis=1, keepdims=True)
        rms[idx] = np.sqrt(np.mean(frames ** 2, axis=1))
        cs = np.concatenate([np.zeros((len(idx), 1)), np.cumsum(frames ** 2, axis=1)], 1)
        et = cs[:, w + taus] - cs[:, taus]  # energy of x[tau:tau+w]
        size = 2 * A_FRAME
        ac = np.fft.irfft(np.fft.rfft(frames, size) * np.conj(np.fft.rfft(frames[:, :w], size)), size)[:, :LAG_HI + 1]
        d = et[:, :1] + et - 2 * ac
        d[:, 0] = 0
        cm = d[:, 1:] * np.arange(1, LAG_HI + 1) / np.maximum(np.cumsum(d[:, 1:], axis=1), 1e-12)
        seg = cm[:, LAG_LO - 1:]
        # YIN: the first dip under 0.15, followed to its bottom; else the deepest point.
        under = seg < 0.15
        first = np.where(under.any(axis=1), under.argmax(axis=1), seg.argmin(axis=1))
        look = np.minimum(first[:, None] + np.arange(8)[None, :], seg.shape[1] - 1)
        best = look[np.arange(len(idx)), np.take_along_axis(seg, look, 1).argmin(axis=1)]
        ap[idx] = seg[np.arange(len(idx)), best]
        f0[idx] = A_SR / (LAG_LO + best)
    return f0, ap, rms


def ensemble_mask(lead: np.ndarray, reference: np.ndarray, sr: int = SR) -> np.ndarray:
    """Per 0.5 s step: True where the model's lead is really many voices (see the module doc)."""
    to_mono = lambda y: signal.resample_poly(np.atleast_2d(y).mean(axis=0), A_SR, sr)  # noqa: E731
    f0, ap, rms = yin(to_mono(lead))
    _, _, ref_rms = yin(to_mono(reference))
    floor = max(np.percentile(ref_rms, 99) * 10 ** (-35 / 20), 1e-6)
    voiced = (rms > floor) & (ap < 0.3)
    semis = 12 * np.log2(np.maximum(f0, 1.0))
    k = 4  # +-40 ms
    steady = np.zeros_like(voiced)
    steady[k:-k] = (voiced[k:-k] & voiced[:-2 * k] & voiced[2 * k:]
                    & (np.abs(semis[2 * k:] - semis[k:-k]) < 0.5) & (np.abs(semis[k:-k] - semis[:-2 * k]) < 0.5))
    step, span = 50, 200  # 0.5 s steps, 2 s windows (in 10 ms frames)
    steps = max(1, int(np.ceil(len(ap) / step)))
    ensemble = np.zeros(steps, dtype=bool)
    for s in range(steps):
        a = max(0, s * step + step // 2 - span // 2)
        sl = slice(a, a + span)
        held = ap[sl][steady[sl]]
        if len(held) >= 20 and float(np.median(held)) >= ENSEMBLE_APERIODICITY:
            ensemble[s] = True
    ensemble = ndimage.median_filter(ensemble.astype(np.uint8), size=5).astype(bool)
    # Only stretches of at least MIN_ENSEMBLE_SECONDS.
    labels, count = ndimage.label(ensemble)
    for i in range(1, count + 1):
        if (labels == i).sum() * 0.5 < MIN_ENSEMBLE_SECONDS:
            ensemble[labels == i] = False
    return ensemble


def _gain(mask: np.ndarray, n: int, sr: int = SR) -> np.ndarray:
    """0.5 s steps to a per-sample gain, with 0.25 s ramps."""
    g = np.repeat(mask.astype(np.float32), int(0.5 * sr))[:n]
    g = np.pad(g, (0, max(0, n - len(g))))
    ramp = int(0.25 * sr)
    return np.convolve(g, np.ones(ramp, np.float32) / ramp, mode="same")[:n]


# ------------------------------------------------------------------ the split


def split(
    vocals: np.ndarray,
    progress: Callable[[float], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    on_download: Callable[[], None] | None = None,
    run: Callable[[np.ndarray], np.ndarray] | None = None,
) -> tuple[dict[str, np.ndarray], dict]:
    """Split a ``(2, n)`` vocals stem at 44.1 kHz into ``{"lead", "choir"}``, which sum back to it.

    Returns the stems and a note of what the clean-up did (seconds moved to the choir). ``run``
    stands in for the model in tests.
    """
    vocals = np.atleast_2d(np.asarray(vocals, dtype=np.float32))
    if vocals.shape[0] == 1:
        vocals = np.vstack([vocals, vocals])
    if run is None:
        ensure(on_download)
        run = _session_run()
    choir = _backing(vocals, run, (lambda f: progress(0.85 * f)) if progress else None, should_stop)
    lead = vocals - choir
    mask = ensemble_mask(lead, vocals)
    g = _gain(mask, vocals.shape[1])
    choir = choir + g * lead
    lead = lead * (1 - g)
    if progress:
        progress(1.0)
    return {"lead": lead.astype(np.float32), "choir": choir.astype(np.float32)}, {
        "choir_led_seconds": round(float(mask.sum()) * 0.5, 1)
    }
