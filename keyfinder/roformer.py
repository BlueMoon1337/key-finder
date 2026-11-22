"""Best quality vocals: Band-Split RoFormer (BS-RoFormer).

The "Best quality" separation engine splits the vocals off with a BS-RoFormer model, which
separates vocals and instrumental more cleanly than Demucs (vocals about 11.8 dB SDR against
htdemucs_ft's 10.8 on the same test, instrumental about 16.5 dB), then lets Demucs split the
instrumental into drums, bass and the rest (separation.py). Demucs gets the instrumental only,
so none of the vocals bleed into its stems.

The model is "BS-RoFormer Viperx 1297" (model_bs_roformer_ep_317_sdr_12.9755), the one UVR and
python-audio-separator use by default. Its network is written out below for inference only, after
lucidrains' BS-RoFormer (MIT) as UVR / python-audio-separator (MIT) adapted it, with its training
loss and the alternatives this model doesn't use left out. The weights (640 MB) are downloaded once,
checked against their SHA-256, and kept in the models folder, so later separations work offline.

Paper: Lu, Wang, Kong, Hung, "Music Source Separation with Band-Split RoPE Transformer" (2023).
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import ssl
import threading
import urllib.request
from collections.abc import Callable
from pathlib import Path

import numpy as np

from .neural import Cancelled, ModelUnavailable, device

SR = 44100

#: The vocal model: its file, where to get it (the audio-separator mirror first, UVR's own release
#: next), its checksum and size.
MODEL = {
    "name": "bs_roformer_1297",
    "file": "model_bs_roformer_ep_317_sdr_12.9755.ckpt",
    "urls": (
        "https://github.com/nomadkaraoke/python-audio-separator/releases/download/model-configs/"
        "model_bs_roformer_ep_317_sdr_12.9755.ckpt",
        "https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/"
        "model_bs_roformer_ep_317_sdr_12.9755.ckpt",
    ),
    "sha256": "5b84f37e8d444c8cb30c79d77f613a41c05868ff9c9ac6c7049c00aefae115aa",
    "size": 639_331_213,
}

#: The model's settings (from its model_bs_roformer_ep_317_sdr_12.9755.yaml).
CONFIG = dict(
    dim=512,
    depth=12,
    stereo=True,
    num_stems=1,
    time_transformer_depth=1,
    freq_transformer_depth=1,
    freqs_per_bands=(2,) * 24 + (4,) * 12 + (12,) * 8 + (24,) * 8 + (48,) * 8 + (128, 129),
    dim_head=64,
    heads=8,
    stft_n_fft=2048,
    stft_hop_length=441,
    stft_win_length=2048,
    mask_estimator_depth=2,
)
#: 8 s at a time (hop × (frames - 1)), with four overlapping passes over every sample on a GPU, as
#: the model's own settings have it, and two on the CPU, which takes half as long for a little less.
CHUNK = 441 * 800
OVERLAP = {"cpu": 2}
OVERLAP_DEFAULT = 4

_models_dir: Path | None = None
_model = None
_lock = threading.Lock()
_download = {"active": False, "error": None, "done": 0}


def available() -> bool:
    """Needs PyTorch and Demucs (for the drums, bass and the rest), as the Demucs engine does."""
    return importlib.util.find_spec("torch") is not None and importlib.util.find_spec("demucs") is not None


def configure(models_dir: Path) -> None:
    global _models_dir
    _models_dir = Path(models_dir) / "roformer"


def _path() -> Path | None:
    return _models_dir / MODEL["file"] if _models_dir else None


def is_downloaded() -> bool:
    p = _path()
    return _model is not None or bool(p and p.exists() and p.with_suffix(".ready").exists())


def status() -> dict:
    """For /api/capabilities: whether the vocal model is here, and how its download is going."""
    return {
        "installed": available(),
        "downloaded": is_downloaded(),
        "downloading": _download["active"],
        "progress": _download["done"] / MODEL["size"] if _download["active"] else None,
        "download_error": _download["error"],
        "size": MODEL["size"],
    }


# ------------------------------------------------------------------------ download


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _fetch(should_stop: Callable[[], bool] | None = None) -> Path:
    """Downloads the weights (once), checking them against their SHA-256 before keeping them."""
    path = _path()
    if path is None:
        raise ModelUnavailable("KeyFinder’s models folder isn’t set up.")
    if is_downloaded():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(".part")
    errors = []
    for url in MODEL["urls"]:
        _download["done"] = 0
        try:
            digest = hashlib.sha256()
            req = urllib.request.Request(url, headers={"User-Agent": "KeyFinder"})
            with urllib.request.urlopen(req, timeout=60, context=_ssl_context()) as res, open(part, "wb") as out:  # noqa: S310
                while chunk := res.read(1 << 20):
                    out.write(chunk)
                    digest.update(chunk)
                    _download["done"] += len(chunk)
                    if should_stop and should_stop():
                        raise Cancelled()
            if digest.hexdigest() != MODEL["sha256"]:
                raise ValueError("the download didn’t match its checksum")
            os.replace(part, path)
            path.with_suffix(".ready").write_text("ok\n")
            return path
        except Cancelled:
            part.unlink(missing_ok=True)
            raise
        except Exception as exc:  # network errors, a moved file, a damaged download: try the next place
            part.unlink(missing_ok=True)
            errors.append(f"{type(exc).__name__}: {str(exc)[:160]}")
    raise ModelUnavailable(
        "Couldn’t download the Best quality vocal model (640 MB). Connect to the internet and try again; "
        f"it’s downloaded only once. ({'; '.join(errors)})"
    )


def download() -> None:
    """Fetch the weights ahead of time (Profile); progress and errors show in :func:`status`."""
    with _lock:
        if _download["active"] or is_downloaded():
            return
        _download.update(active=True, error=None, done=0)

    def run():
        try:
            _fetch()
        except Exception as exc:  # noqa: BLE001 - reported through status()
            _download["error"] = str(exc)
        finally:
            _download["active"] = False

    threading.Thread(target=run, name="download-roformer", daemon=True).start()


def load(on_download: Callable[[], None] | None = None, should_stop: Callable[[], bool] | None = None):
    """The vocal model, downloading its weights first if needed."""
    global _model
    with _lock:
        if _model is not None:
            return _model
    if not is_downloaded() and on_download:
        on_download()
    path = _fetch(should_stop)
    import torch

    with _lock:
        if _model is None:
            net = _network()(**CONFIG)
            state = torch.load(path, map_location="cpu", weights_only=True)
            net.load_state_dict(state)
            _model = net.to(device()).eval()
        return _model


# ------------------------------------------------------------------------ separation


def separate_vocals(
    y: np.ndarray,
    progress: Callable[[float], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    on_download: Callable[[], None] | None = None,
) -> np.ndarray:
    """The vocals of a ``(2, n)`` signal at 44.1 kHz, as ``(2, n)``.

    The song is processed 8 s at a time, each sample covered by four overlapping windows that are
    blended (Hamming-weighted), as the model's own inference does.
    """
    import torch

    model = load(on_download, should_stop)
    run_on = next(model.parameters()).device
    mix = np.atleast_2d(np.asarray(y, dtype=np.float32))
    if mix.shape[0] == 1:
        mix = np.repeat(mix, 2, axis=0)
    n = mix.shape[1]
    # A song shorter than one window is padded to it.
    padded = np.pad(mix, ((0, 0), (0, max(0, CHUNK - n))))
    total = padded.shape[1]
    passes = int(os.environ.get("KEYFINDER_ROFORMER_OVERLAP") or OVERLAP.get(run_on.type, OVERLAP_DEFAULT))
    step = CHUNK // max(1, passes)
    starts = list(range(0, max(1, total - CHUNK) + 1, step))
    if starts[-1] + CHUNK < total:
        starts.append(total - CHUNK)

    window = torch.hamming_window(CHUNK, periodic=False, dtype=torch.float32)
    result = torch.zeros((2, total), dtype=torch.float32)
    weight = torch.zeros(total, dtype=torch.float32)
    source = torch.from_numpy(padded)
    autocast = torch.autocast("cuda", dtype=torch.float16) if run_on.type == "cuda" else _nullcontext()
    with torch.no_grad(), autocast:
        for i, start in enumerate(starts):
            part = source[:, start : start + CHUNK].to(run_on)
            out = model(part[None])[0].float().cpu()
            length = min(CHUNK, out.shape[-1])
            result[:, start : start + length] += out[:, :length] * window[:length]
            weight[start : start + length] += window[:length]
            if progress:
                progress((i + 1) / len(starts))
            if should_stop and should_stop():
                raise Cancelled()
    vocals = (result / weight.clamp(min=1e-10)).numpy()[:, :n]
    return np.ascontiguousarray(vocals, dtype=np.float32)


class _nullcontext:
    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False


# ------------------------------------------------------------------------ the network

_NETWORK = None


def _network():
    """The BSRoformer class, defined on first use so that importing this module doesn't import torch."""
    global _NETWORK
    if _NETWORK is not None:
        return _NETWORK

    import torch
    import torch.nn.functional as F
    from torch import nn

    class RMSNorm(nn.Module):
        def __init__(self, dim):
            super().__init__()
            self.scale = dim**0.5
            self.gamma = nn.Parameter(torch.ones(dim))

        def forward(self, x):
            return F.normalize(x, dim=-1) * self.scale * self.gamma

    class Rotary(nn.Module):
        """Rotary position embedding over the whole head (as rotary-embedding-torch, theta 10000)."""

        def __init__(self, dim):
            super().__init__()
            freqs = 1.0 / (10000 ** (torch.arange(0, dim, 2).float() / dim))
            self.freqs = nn.Parameter(freqs, requires_grad=False)

        def forward(self, t):
            n = t.shape[-2]
            angles = torch.arange(n, device=t.device, dtype=torch.float32)[:, None] * self.freqs.float()[None]
            angles = angles.repeat_interleave(2, dim=-1)
            # Pairs (x1, x2) → (-x2, x1).
            pairs = t.float().unflatten(-1, (-1, 2))
            rotated = torch.stack((-pairs[..., 1], pairs[..., 0]), dim=-1).flatten(-2)
            return (t.float() * angles.cos() + rotated * angles.sin()).to(t.dtype)

    class Attention(nn.Module):
        def __init__(self, dim, heads, dim_head, rotary):
            super().__init__()
            self.heads = heads
            self.rotary_embed = rotary
            self.norm = RMSNorm(dim)
            self.to_qkv = nn.Linear(dim, heads * dim_head * 3, bias=False)
            self.to_gates = nn.Linear(dim, heads)
            self.to_out = nn.Sequential(nn.Linear(heads * dim_head, dim, bias=False), nn.Dropout(0.0))

        def forward(self, x):
            x = self.norm(x)
            b, n, _ = x.shape
            q, k, v = self.to_qkv(x).view(b, n, 3, self.heads, -1).permute(2, 0, 3, 1, 4)
            q, k = self.rotary_embed(q), self.rotary_embed(k)
            out = F.scaled_dot_product_attention(q, k, v)
            out = out * self.to_gates(x).transpose(1, 2)[..., None].sigmoid()
            return self.to_out(out.transpose(1, 2).reshape(b, n, -1))

    class FeedForward(nn.Module):
        def __init__(self, dim, mult=4):
            super().__init__()
            self.net = nn.Sequential(
                RMSNorm(dim), nn.Linear(dim, dim * mult), nn.GELU(), nn.Dropout(0.0),
                nn.Linear(dim * mult, dim), nn.Dropout(0.0),
            )

        def forward(self, x):
            return self.net(x)

    class Transformer(nn.Module):
        def __init__(self, dim, depth, heads, dim_head, rotary):
            super().__init__()
            self.layers = nn.ModuleList(
                nn.ModuleList([Attention(dim, heads, dim_head, rotary), FeedForward(dim)]) for _ in range(depth)
            )

        def forward(self, x):
            for attn, ff in self.layers:
                x = attn(x) + x
                x = ff(x) + x
            return x

    class BandSplit(nn.Module):
        def __init__(self, dim, dim_inputs):
            super().__init__()
            self.dim_inputs = dim_inputs
            self.to_features = nn.ModuleList(nn.Sequential(RMSNorm(d), nn.Linear(d, dim)) for d in dim_inputs)

        def forward(self, x):
            parts = x.split(self.dim_inputs, dim=-1)
            return torch.stack([f(part) for part, f in zip(parts, self.to_features, strict=True)], dim=-2)

    def mlp(dim_in, dim_out, dim_hidden, depth):
        dims = (dim_in, *((dim_hidden,) * (depth - 1)), dim_out)
        layers = []
        for i, (a, b) in enumerate(zip(dims[:-1], dims[1:], strict=True)):
            layers.append(nn.Linear(a, b))
            if i < len(dims) - 2:
                layers.append(nn.Tanh())
        return nn.Sequential(*layers)

    class MaskEstimator(nn.Module):
        def __init__(self, dim, dim_inputs, depth, expansion=4):
            super().__init__()
            self.to_freqs = nn.ModuleList(
                nn.Sequential(mlp(dim, d * 2, dim * expansion, depth), nn.GLU(dim=-1)) for d in dim_inputs
            )

        def forward(self, x):
            return torch.cat([f(band) for band, f in zip(x.unbind(dim=-2), self.to_freqs, strict=True)], dim=-1)

    class BSRoformer(nn.Module):
        def __init__(self, dim, *, depth, stereo, num_stems, time_transformer_depth, freq_transformer_depth,
                     freqs_per_bands, dim_head, heads, stft_n_fft, stft_hop_length, stft_win_length,
                     mask_estimator_depth):
            super().__init__()
            self.channels = 2 if stereo else 1
            self.num_stems = num_stems
            time_rotary, freq_rotary = Rotary(dim_head), Rotary(dim_head)
            self.layers = nn.ModuleList(
                nn.ModuleList([
                    Transformer(dim, time_transformer_depth, heads, dim_head, time_rotary),
                    Transformer(dim, freq_transformer_depth, heads, dim_head, freq_rotary),
                ])
                for _ in range(depth)
            )
            self.final_norm = RMSNorm(dim)
            self.stft = dict(n_fft=stft_n_fft, hop_length=stft_hop_length, win_length=stft_win_length, normalized=False)
            self.win_length = stft_win_length
            dims = tuple(2 * f * self.channels for f in freqs_per_bands)
            self.band_split = BandSplit(dim, dims)
            self.mask_estimators = nn.ModuleList(
                MaskEstimator(dim, dims, mask_estimator_depth) for _ in range(num_stems)
            )

        def forward(self, audio):
            # (b, s, t) → spectrogram. Apple's GPU doesn't do every complex operation: those run on the CPU.
            on = audio.device
            spectral = torch.device("cpu") if on.type == "mps" else on
            b, s, t = audio.shape
            window = torch.hann_window(self.win_length, device=spectral)
            spec = torch.stft(audio.to(spectral).reshape(b * s, t), **self.stft, window=window, return_complex=True)
            spec = torch.view_as_real(spec)  # (b s, f, frames, 2)
            f, frames = spec.shape[1], spec.shape[2]
            spec = spec.reshape(b, s, f, frames, 2).permute(0, 2, 1, 3, 4).reshape(b, f * s, frames, 2)
            x = spec.permute(0, 2, 1, 3).reshape(b, frames, f * s * 2).to(on)
            x = self.band_split(x)  # (b, frames, bands, d)
            for time_transformer, freq_transformer in self.layers:
                bands = x.shape[2]
                x = x.permute(0, 2, 1, 3).reshape(b * bands, frames, -1)
                x = time_transformer(x)
                x = x.reshape(b, bands, frames, -1).permute(0, 2, 1, 3).reshape(b * frames, bands, -1)
                x = freq_transformer(x)
                x = x.reshape(b, frames, bands, -1)
            x = self.final_norm(x)
            mask = torch.stack([m(x) for m in self.mask_estimators], dim=1)  # (b, n, frames, f s 2)
            mask = mask.reshape(b, self.num_stems, frames, f * s, 2).permute(0, 1, 3, 2, 4)
            masked = torch.view_as_complex(spec[:, None].contiguous()) * torch.view_as_complex(
                mask.to(spectral, torch.float32).contiguous()
            )
            masked = masked.reshape(b * self.num_stems, f, s, frames).permute(0, 2, 1, 3).reshape(-1, f, frames)
            out = torch.istft(masked, **self.stft, window=window, return_complex=False)
            out = out.reshape(b, self.num_stems, s, -1).to(on)
            return out[:, 0] if self.num_stems == 1 else out

    _NETWORK = BSRoformer
    return _NETWORK
