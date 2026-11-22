"""Stem separation.

Three backends:

* ``best`` - best quality: the vocals split off with a BS-RoFormer model (roformer.py), then the
  instrumental split by Demucs' fine-tuned model (htdemucs_ft; htdemucs_6s for 6 stems). Cleaner
  vocals, and no vocal bleed in the other stems, for a few times the time Demucs takes. Chosen
  explicitly; it needs the same install as Demucs, and downloads its vocal model (640 MB) once.
* ``demucs`` - Meta's Hybrid Transformer Demucs, a neural model with
  state-of-the-art quality (see neural.py). Used automatically when the
  ``demucs`` package is installed: it's bundled in the desktop app, and
  ``pip install -e .[ml]`` adds it to a source checkout.
* ``dsp`` - a dependency-free fallback using harmonic/percussive median
  filtering, stereo centre extraction and frequency crossovers. It is fast
  and always available but much rougher; it is meant for practice use
  (e.g. turning the drums down) rather than clean isolation.

Both return stems whose sum reconstructs the input mix.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import numpy as np
from scipy import ndimage, signal

from . import audio, neural, roformer, vocal_split

Progress = Callable[[float], None]

MODES = {
    "2stems": ("vocals", "accompaniment"),
    "4stems": ("vocals", "drums", "bass", "other"),
    "6stems": ("vocals", "drums", "bass", "guitar", "piano", "other"),
}
DSP_MODES = ("2stems", "4stems")


def stem_names(mode: str, choir: bool = False, strings: bool = False) -> tuple[str, ...]:
    """The stems a separation makes: the mode's, with vocals as lead and choir, and strings & pads
    out of the other instruments, when asked."""
    names = list(MODES[mode])
    if strings:
        names.insert(names.index("other") if "other" in names else len(names) - 1, "strings")
    if choir:
        i = names.index("vocals")
        names[i:i + 1] = ["lead", "choir"]
    return tuple(names)


def check_extras(backend: str, choir: bool, strings: bool) -> None:
    """Choir and strings need a neural separator, Demucs or Best quality (and the choir its model runner)."""
    if (choir or strings) and backend not in ("demucs", "best"):
        raise ValueError("choir and strings isolation need the Demucs separator (or Best quality)")
    if choir and not vocal_split.available():
        raise ValueError("choir isolation needs onnxruntime (pip install -e .[ml])")


def demucs_available() -> bool:
    return neural.available()


def best_available() -> bool:
    return roformer.available()


def available_backends() -> list[str]:
    return (["best"] if best_available() else []) + (["demucs"] if demucs_available() else []) + ["dsp"]


def choose_backend(requested: str = "auto", mode: str = "4stems") -> str:
    if requested == "auto":
        return "demucs" if demucs_available() else "dsp"
    if requested in ("demucs", "best") and not demucs_available():
        raise ValueError(f"the {requested} backend is not installed (pip install -e .[ml])")
    if requested == "dsp" and mode not in DSP_MODES:
        raise ValueError(f"the dsp backend supports {', '.join(DSP_MODES)} only")
    if requested not in ("best", "demucs", "dsp"):
        raise ValueError(f"unknown backend {requested!r}")
    return requested


#: Best quality: the Demucs model that splits the instrumental, by mode (2 stems uses it to find
#: any voice the vocal model left behind).
BEST_DEMUCS = {"2stems": "htdemucs_ft", "4stems": "htdemucs_ft", "6stems": "htdemucs_6s"}
#: Best quality: the share of the work the vocal model takes (the rest is Demucs).
BEST_VOCALS_SHARE = 0.55


def separate_best(
    y: np.ndarray,
    mode: str,
    progress: Progress | None = None,
    should_stop: Callable[[], bool] | None = None,
    on_download: Callable[[str], None] | None = None,
) -> dict[str, np.ndarray]:
    """Vocals with BS-RoFormer, then the instrumental (the mix less those vocals) with Demucs.

    BS-RoFormer's vocals are the cleanest, but on a voice buried low in the mix it can leave part
    of it behind; Demucs, splitting the instrumental, finds that part as "vocals", and it goes back
    to the vocals. (On MUSDB18 test songs this took a rap vocal from 1.5 to 7.7 dB SDR, against
    Demucs' 5.5, for half a dB on a clear one, which stayed at 11.5 against Demucs' 6.4.)
    "Other" is the instrumental less the named instruments, so the stems add up to the mix.
    """
    y = np.atleast_2d(np.asarray(y, dtype=np.float32))
    if y.shape[0] == 1:
        y = np.repeat(y, 2, axis=0)
    share = BEST_VOCALS_SHARE
    vocals = roformer.separate_vocals(
        y,
        (lambda f: progress(share * f)) if progress else None,
        should_stop,
        (lambda: on_download("vocals")) if on_download else None,
    )
    instrumental = y - vocals
    parts = neural.separate(
        instrumental,
        "6stems" if mode == "6stems" else "4stems",
        (lambda f: progress(share + (1 - share) * f)) if progress else None,
        should_stop,
        (lambda: on_download("instruments")) if on_download else None,
        # KEYFINDER_DEMUCS_MODEL stands in for it, as for the Demucs engine (tests use Demucs' test model).
        model_name=(os.environ.get("KEYFINDER_DEMUCS_MODEL") if mode != "6stems" else None) or BEST_DEMUCS[mode],
    )
    missed = parts.pop("vocals")
    vocals = vocals + missed
    instrumental = instrumental - missed
    if mode == "2stems":
        return {"vocals": vocals, "accompaniment": instrumental}
    parts["other"] = instrumental - sum(v for k, v in parts.items() if k != "other")
    return {"vocals": vocals, **parts}


def separate(
    path: str | Path,
    mode: str = "4stems",
    backend: str = "auto",
    progress: Progress | None = None,
    should_stop: Callable[[], bool] | None = None,
    on_download: Callable[[], None] | None = None,
    choir: bool = False,
    strings: bool = False,
    on_choir_download: Callable[[], None] | None = None,
    notes: dict | None = None,
) -> tuple[dict[str, np.ndarray], int]:
    """Split the file at ``path`` into stereo stems ``{name: (2, n)}``; returns (stems, sample_rate).

    ``progress`` gets 0..1 as the work goes; ``should_stop`` is asked now and then and
    cancels the separation (raising :class:`neural.Cancelled`) when it answers True.
    ``on_download`` is called before the Demucs model is downloaded the first time, and
    ``on_choir_download`` before the choir model is. ``choir`` splits the vocals into lead and
    choir; ``strings`` takes strings & pads out of the other instruments (both need Demucs).
    ``notes``, if given, collects what the choir clean-up did.
    """
    if mode not in MODES:
        raise ValueError(f"unknown separation mode {mode!r}; choose from {', '.join(MODES)}")
    backend = choose_backend(backend, mode)
    check_extras(backend, choir, strings)
    y = audio.load(path, audio.SEPARATION_SR, mono=False)
    if backend in ("best", "demucs"):
        if backend == "best":
            best_download = (lambda _which: on_download()) if on_download else None

            def base(y, m, p, stop):
                return separate_best(y, m, p, stop, best_download)
        else:

            def base(y, m, p, stop):
                return neural.separate(y, m, p, stop, on_download)

        if not (choir or strings):
            return base(y, mode, progress, should_stop), audio.SEPARATION_SR
        return _separate_extra(base, y, mode, choir, strings, progress, should_stop, on_choir_download,
                               notes), audio.SEPARATION_SR
    if mode not in DSP_MODES:
        mode = "4stems"
    return separate_dsp(y, audio.SEPARATION_SR, mode, progress, should_stop), audio.SEPARATION_SR


def _separate_extra(base, y, mode, choir, strings, progress, should_stop, on_choir_download, notes):
    """``base`` (Demucs or Best quality), then the choir and strings splits on its stems."""
    # Demucs takes most of the time; the choir model about half as long again.
    share = 0.6 if choir else 0.9
    report = (lambda lo, span: (lambda f: progress(lo + span * f))) if progress else (lambda lo, span: None)
    stems = base(y, "6stems" if strings else mode, report(0.0, share), should_stop)
    if strings:
        held, rest = split_strings(stems.pop("other"), audio.SEPARATION_SR,
                                   report(share, 0.1 if choir else 1 - share))
        stems["strings"], stems["other"] = held, rest
        if mode != "6stems":  # back to the mode's stems: guitar and piano join the other instruments
            stems["other"] = stems["other"] + stems.pop("guitar") + stems.pop("piano")
        if mode == "2stems":
            stems["accompaniment"] = stems.pop("drums") + stems.pop("bass") + stems.pop("other")
    if choir:
        if should_stop and should_stop():
            raise neural.Cancelled()
        start = share + (0.1 if strings else 0.0)
        try:
            parts, info = vocal_split.split(stems.pop("vocals"), report(start, 1 - start), should_stop,
                                            on_choir_download)
        except vocal_split.Cancelled:
            raise neural.Cancelled() from None
        stems.update(parts)
        if notes is not None:
            notes.update(info)
    return {name: stems[name] for name in stem_names(mode, choir, strings)}


# --------------------------------------------------------------------------- dsp

N_FFT = 4096
HOP = 1024
BLOCK_SECONDS = 30.0
PAD_SECONDS = 2.0


def _soft_mask(target: np.ndarray, other: np.ndarray, power: float = 2.0) -> np.ndarray:
    t, o = target ** power, other ** power
    return t / np.maximum(t + o, 1e-12)


def _masks(spec_l: np.ndarray, spec_r: np.ndarray, sr: int, mode: str) -> dict[str, np.ndarray]:
    """Time-frequency masks that sum to one in every bin."""
    mag = 0.5 * (np.abs(spec_l) + np.abs(spec_r))
    # Fitzgerald HPSS: sustained notes are smooth along time, hits along frequency.
    harmonic = ndimage.median_filter(mag, size=(1, 17))
    percussive = ndimage.median_filter(mag, size=(17, 1))
    perc_mask = _soft_mask(percussive, harmonic)

    freqs = np.fft.rfftfreq(N_FFT, 1.0 / sr)[:, None]
    # Centre-panned energy: left and right nearly identical in level and phase.
    cross = np.abs(spec_l * np.conj(spec_r))
    power = np.abs(spec_l) ** 2 + np.abs(spec_r) ** 2
    similarity = np.real(spec_l * np.conj(spec_r)) / np.maximum(0.5 * power, 1e-12)
    centre = np.clip(similarity, 0.0, 1.0) * (2 * cross / np.maximum(power, 1e-12))
    centre = ndimage.uniform_filter(centre, size=(3, 5)) ** 4
    # Most lead-vocal energy lies between ~120 Hz and ~7 kHz.
    vocal_band = 1.0 / (1.0 + (120.0 / np.maximum(freqs, 1.0)) ** 4) / (1.0 + (freqs / 7000.0) ** 4)

    harm_mask = 1.0 - perc_mask
    vocals = harm_mask * centre * vocal_band
    if mode == "2stems":
        return {"vocals": vocals, "accompaniment": 1.0 - vocals}

    low = 1.0 / (1.0 + (freqs / 180.0) ** 6)  # crossover for the bass stem
    drums = perc_mask * (1.0 - 0.5 * low)      # kick fundamentals share the bass band
    bass = (1.0 - drums) * low
    vocals = vocals * (1.0 - low)
    other = np.clip(1.0 - drums - bass - vocals, 0.0, 1.0)
    return {"vocals": vocals, "drums": drums, "bass": bass, "other": other}


def _separate_block(y: np.ndarray, sr: int, mode: str) -> dict[str, np.ndarray]:
    if y.shape[0] == 1:
        y = np.vstack([y, y])
    _, _, spec = signal.stft(y, sr, nperseg=N_FFT, noverlap=N_FFT - HOP)
    masks = _masks(spec[0], spec[1], sr, mode)
    stems = {}
    for name, mask in masks.items():
        _, out = signal.istft(spec * mask[None], sr, nperseg=N_FFT, noverlap=N_FFT - HOP)
        stems[name] = out[:, : y.shape[1]].astype(np.float32)
    return stems


def separate_dsp(y: np.ndarray, sr: int, mode: str = "4stems", progress: Progress | None = None,
                 should_stop: Callable[[], bool] | None = None) -> dict[str, np.ndarray]:
    """Separate a ``(channels, n)`` signal in overlapping blocks to bound memory use."""
    y = np.atleast_2d(np.asarray(y, dtype=np.float32))
    n = y.shape[1]
    block = int(BLOCK_SECONDS * sr)
    pad = int(PAD_SECONDS * sr)
    names = MODES[mode]
    out = {name: np.zeros((2, n), dtype=np.float32) for name in names}
    for start in range(0, n, block):
        lo, hi = max(0, start - pad), min(n, start + block + pad)
        stems = _separate_block(y[:, lo:hi], sr, mode)
        keep = slice(start - lo, start - lo + min(block, n - start))
        for name in names:
            out[name][:, start:start + min(block, n - start)] = stems[name][:, keep]
        if progress:
            progress(min(1.0, (start + block) / n))
        if should_stop and should_stop():
            raise neural.Cancelled()
    return out


# --------------------------------------------------------------------------- strings & pads

STRINGS_HOLD_SECONDS = 0.75  # a sound held about this long counts as strings or a pad


def split_strings(other: np.ndarray, sr: int, progress: Progress | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Split Demucs' 6-stem "other" (what's left once vocals, drums, bass, guitar and piano are out)
    into strings & pads and the rest. Bowed strings and pads hold their notes; what's left of the
    other instruments is mostly shorter. No model is trained for strings, so synth pads, organ or
    held brass come through with them. The two parts sum to ``other``.
    """
    other = np.atleast_2d(np.asarray(other, dtype=np.float32))
    n = other.shape[1]
    block, pad = int(BLOCK_SECONDS * sr), int(PAD_SECONDS * sr)
    strings = np.zeros_like(other)
    hold = max(3, int(round(STRINGS_HOLD_SECONDS * sr / HOP)) | 1)
    freqs = np.fft.rfftfreq(N_FFT, 1.0 / sr)[:, None]
    band = 1.0 / (1.0 + (100.0 / np.maximum(freqs, 1.0)) ** 4) / (1.0 + (freqs / 12000.0) ** 4)
    for start in range(0, n, block):
        lo, hi = max(0, start - pad), min(n, start + block + pad)
        y = other[:, lo:hi]
        _, _, spec = signal.stft(y, sr, nperseg=N_FFT, noverlap=N_FFT - HOP)
        mag = np.abs(spec).mean(axis=0)
        # Held: what stays for `hold` frames, letting vibrato wander a couple of bins (+-20 Hz).
        held = np.minimum(ndimage.median_filter(ndimage.maximum_filter(mag, size=(5, 1)), size=(1, hold)), mag)
        brief = np.maximum(mag - held, 0.0) + ndimage.median_filter(mag, size=(17, 1)) * 0.5
        mask = _soft_mask(held, brief) * band
        _, out = signal.istft(spec * mask[None], sr, nperseg=N_FFT, noverlap=N_FFT - HOP)
        keep = slice(start - lo, start - lo + min(block, n - start))
        strings[:, start:start + min(block, n - start)] = out[:, : y.shape[1]][:, keep]
        if progress:
            progress(min(1.0, (start + block) / n))
    return strings, other - strings

