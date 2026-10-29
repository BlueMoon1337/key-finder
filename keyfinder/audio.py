"""Audio I/O built on PyAV (FFmpeg's libraries, bundled in its wheels).

Using the libraries rather than the ``ffmpeg`` command means the desktop app
has nothing extra to install: any format FFmpeg understands (mp3, m4a, flac,
wav, ogg, wma, video files with an audio track, ...) decodes out of the box.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import av
import av.error
import av.filter
import numpy as np

ANALYSIS_SR = 22050
SEPARATION_SR = 44100
CHUNK = 8192  # samples per frame pushed through encoders and filter graphs

# Output format by file extension: (container format, codec, bitrate or None).
ENCODERS = {
    ".mp3": ("mp3", "libmp3lame", 192_000),
    ".m4a": ("ipod", "aac", 192_000),
    ".wav": ("wav", "pcm_s16le", None),
    ".flac": ("flac", "flac", None),
}


class AudioError(RuntimeError):
    pass


def _layout(channels: int) -> str:
    return "mono" if channels == 1 else "stereo"


def load(path: str | Path, sr: int = ANALYSIS_SR, mono: bool = True) -> np.ndarray:
    """Decode ``path`` to float32 samples in [-1, 1].

    Returns shape ``(n,)`` when ``mono`` else ``(2, n)``.
    """
    channels = 1 if mono else 2
    try:
        with av.open(str(path)) as container:
            if not container.streams.audio:
                raise AudioError(f"{Path(path).name} has no audio track")
            stream = container.streams.audio[0]
            resampler = av.AudioResampler(format="fltp", layout=_layout(channels), rate=sr)
            parts = []
            for frame in container.decode(stream):
                parts.extend(f.to_ndarray() for f in resampler.resample(frame))
            parts.extend(f.to_ndarray() for f in resampler.resample(None))
    except av.error.FFmpegError as exc:
        raise AudioError(f"could not decode {Path(path).name}: {exc}") from exc
    if not parts:
        raise AudioError(f"{Path(path).name} contains no audio")
    y = np.concatenate(parts, axis=1).astype(np.float32)
    return y[0] if mono else y


def _frames(y: np.ndarray, sr: int):
    """Yield planar float frames of ``CHUNK`` samples with running timestamps."""
    y = np.ascontiguousarray(np.atleast_2d(y), dtype=np.float32)
    layout = _layout(y.shape[0])
    for start in range(0, y.shape[1], CHUNK):
        chunk = np.ascontiguousarray(y[:, start:start + CHUNK])
        frame = av.AudioFrame.from_ndarray(chunk, format="fltp", layout=layout)
        frame.sample_rate = sr
        frame.pts = start
        frame.time_base = Fraction(1, sr)
        yield frame


def save(path: str | Path, y: np.ndarray, sr: int, bitrate: int | None = None) -> None:
    """Encode samples (``(n,)`` or ``(channels, n)``) to ``path``; the codec follows the extension."""
    suffix = Path(path).suffix.lower()
    if suffix not in ENCODERS:
        raise AudioError(f"cannot write {suffix or 'files without an extension'}; use {', '.join(ENCODERS)}")
    fmt, codec, default_rate = ENCODERS[suffix]
    y = np.clip(np.atleast_2d(np.asarray(y, dtype=np.float32)), -1.0, 1.0)
    layout = _layout(y.shape[0])
    try:
        with av.open(str(path), "w", format=fmt) as out:
            stream = out.add_stream(codec, rate=sr, layout=layout)
            if default_rate:
                stream.bit_rate = bitrate or default_rate
            resampler = av.AudioResampler(format=stream.codec_context.format.name, layout=layout, rate=sr)
            fifo = av.AudioFifo()
            frame_size = stream.codec_context.frame_size or CHUNK

            def encode(frame):
                for packet in stream.encode(frame):
                    out.mux(packet)

            for frame in _frames(y, sr):
                for converted in resampler.resample(frame):
                    fifo.write(converted)
                while fifo.samples >= frame_size:
                    encode(fifo.read(frame_size))
            for converted in resampler.resample(None):
                fifo.write(converted)
            if fifo.samples:
                encode(fifo.read())  # a short last frame is allowed
            encode(None)
    except av.error.FFmpegError as exc:
        Path(path).unlink(missing_ok=True)
        raise AudioError(f"could not encode {Path(path).name}: {exc}") from exc


def apply_filters(y: np.ndarray, sr: int, filters: list[tuple[str, str]]) -> np.ndarray:
    """Run samples through an FFmpeg filter chain such as ``[("atempo", "0.8")]``.

    The result keeps the input's channel count and sample rate.
    """
    y = np.atleast_2d(np.asarray(y, dtype=np.float32))
    if not filters:
        return y.copy()
    layout = _layout(y.shape[0])
    graph = av.filter.Graph()
    node = graph.add_abuffer(format="fltp", sample_rate=sr, layout=layout, time_base=Fraction(1, sr))
    chain = [*filters, ("aformat", f"sample_fmts=fltp:sample_rates={sr}:channel_layouts={layout}")]
    for name, args in chain:
        nxt = graph.add(name, args)
        node.link_to(nxt)
        node = nxt
    sink = graph.add("abuffersink")
    node.link_to(sink)
    graph.configure()

    parts: list[np.ndarray] = []

    def drain():
        while True:
            try:
                parts.append(graph.pull().to_ndarray())
            except (av.error.BlockingIOError, av.error.EOFError):
                return

    for frame in _frames(y, sr):
        graph.push(frame)
        drain()
    graph.push(None)
    drain()
    if not parts:
        return np.zeros((y.shape[0], 0), dtype=np.float32)
    return np.concatenate(parts, axis=1).astype(np.float32)


def waveform_peaks(y: np.ndarray, points: int = 1200) -> list[float]:
    """Downsampled peak envelope for drawing a waveform overview."""
    y = np.abs(np.asarray(y))
    if y.ndim > 1:
        y = y.max(axis=0)
    if y.size == 0:
        return []
    points = min(points, y.size)
    edges = np.linspace(0, y.size, points + 1).astype(int)
    peaks = np.maximum.reduceat(y, edges[:-1])
    top = peaks.max() or 1.0
    return [round(float(p), 4) for p in peaks / top]


def probe(path: str | Path) -> dict:
    """Title/artist tags, duration and whether there is cover art or video."""
    try:
        with av.open(str(path)) as container:
            tags = {k.lower(): v for k, v in (container.metadata or {}).items()}
            for stream in container.streams.audio[:1]:
                for k, v in (stream.metadata or {}).items():
                    tags.setdefault(k.lower(), v)
            pictures = [_is_attached_pic(s) for s in container.streams.video]
            duration = (container.duration or 0) / av.time_base
    except av.error.FFmpegError:
        return {}
    return {
        "title": (tags.get("title") or "").strip(),
        "artist": (tags.get("artist") or tags.get("album_artist") or "").strip(),
        "duration": float(duration),
        "cover": any(pictures),
        "video": not all(pictures),
    }


def _is_attached_pic(stream) -> bool:
    return bool(stream.disposition & av.stream.Disposition.attached_pic)


def extract_cover(path: str | Path, dest: str | Path, size: int = 320, at: float = 0.0) -> bool:
    """Save embedded cover art (or a video frame ``at`` seconds in) as a square-ish JPEG."""
    try:
        with av.open(str(path)) as container:
            streams = sorted(container.streams.video, key=lambda s: not _is_attached_pic(s))
            if not streams:
                return False
            stream = streams[0]
            if at > 0 and not _is_attached_pic(stream):
                container.seek(int(at / stream.time_base), stream=stream)
            frame = next(container.decode(stream), None)
            if frame is None:
                return False
            scale = size / min(frame.width, frame.height)
            width = max(2, int(frame.width * scale) // 2 * 2)
            height = max(2, int(frame.height * scale) // 2 * 2)
            image = frame.reformat(width=width, height=height, format="yuvj420p")
            encoder = av.CodecContext.create("mjpeg", "w")
            encoder.width, encoder.height = width, height
            encoder.pix_fmt = "yuvj420p"
            encoder.time_base = Fraction(1, 25)
            packets = [*encoder.encode(image), *encoder.encode(None)]
    except (av.error.FFmpegError, StopIteration, ValueError):
        return False
    if not packets:
        return False
    Path(dest).write_bytes(b"".join(bytes(p) for p in packets))
    return True
