"""Lyrics timed to the word, for showing the chords over the words as a song plays.

Two sources, used together:

* **LRCLIB** (lrclib.net), a free database of song lyrics, many with a time for each line.
  KeyFinder looks the song up by its title, artist and length. Its text is spelled right,
  which a transcription can't promise.
* **Whisper** (OpenAI's speech recognition, run here with faster-whisper), on the song's vocals
  stem: every word with its start and end. It runs on this computer; the model is downloaded
  once, like Demucs'.

When both are there, LRCLIB's words are matched to Whisper's to time each one, and the match
also tells whether LRCLIB's lyrics are of this recording at all (a live version can differ
from the studio one). Without a match, Whisper's own words are used; without Whisper (online
only), LRCLIB's line times are kept and the words spread across each line.

Lines follow the singing: a new line at a pause, at the end of a phrase (a comma or a full
stop, once a line has a few words) or after nine words, as chord charts set them.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import threading
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np

from . import __version__

SR = 16000  # what Whisper listens at
MODEL = os.environ.get("KEYFINDER_WHISPER_MODEL", "large-v3-turbo")
MODEL_MB = 1600
LRCLIB = os.environ.get("KEYFINDER_LRCLIB", "https://lrclib.net")
USER_AGENT = f"KeyFinder/{__version__} (https://github.com/BlueMoon1337/key-finder)"
MODES = ("auto", "online", "off")  # LRCLIB and Whisper, LRCLIB only, no lyrics

LINE_GAP = 0.8  # seconds of silence that end a line once it has MIN_PHRASE_WORDS...
LONG_GAP = 2.5  # ...and that end it however short it is (a held "No…" before the rest stays one line)
MAX_LINE_WORDS = 9
MIN_PHRASE_WORDS = 3  # a comma ends a line once it has this many words
LRCLIB_MATCH = 0.35  # share of LRCLIB's words Whisper must hear for its lyrics to be this song's
DURATION_SLACK = 15.0  # seconds LRCLIB's length may differ from the song's

# Things Whisper is known to write when it hears music and no words (subtitle credits, sign-offs).
HALLUCINATIONS = re.compile(
    r"amara\.org|subt[ií]tulos|suscr[ií]bete|gracias por ver|thanks for watching|subscribe|"
    r"www\.|\.com\b|música\s*$|^\s*\[?m[uú]sica\]?\s*$|^\s*♪+\s*$",
    re.IGNORECASE,
)

_models_dir: Path | None = None
_cache: dict[str, object] = {}
_lock = threading.Lock()
_download = {"active": False, "error": None}


class Cancelled(Exception):
    """The song was deleted while its lyrics were being found."""


class ModelUnavailable(RuntimeError):
    """The Whisper model isn't on this computer and couldn't be downloaded."""


# ------------------------------------------------------------------ Whisper


def available() -> bool:
    return importlib.util.find_spec("faster_whisper") is not None


def configure(models_dir: Path) -> None:
    global _models_dir
    _models_dir = Path(models_dir)
    (_models_dir / "whisper").mkdir(parents=True, exist_ok=True)


def _marker() -> Path | None:
    return _models_dir / f"whisper-{MODEL}.ready" if _models_dir else None


def is_downloaded() -> bool:
    marker = _marker()
    return bool(marker and marker.exists()) or MODEL in _cache


def status() -> dict:
    """For /api/capabilities: whether transcription can run, and whether its model is here."""
    if not available():
        return {"installed": False}
    return {"installed": True, "model": MODEL, "size_mb": MODEL_MB, "downloaded": is_downloaded(),
            "downloading": _download["active"], "download_error": _download["error"]}


def load(on_download: Callable[[], None] | None = None):
    """The Whisper model, downloaded from the Hugging Face hub the first time (once per computer)."""
    with _lock:
        if MODEL in _cache:
            return _cache[MODEL]
        if on_download and not is_downloaded():
            on_download()
        from faster_whisper import WhisperModel

        try:
            import ctranslate2

            cuda = ctranslate2.get_cuda_device_count() > 0
        except Exception:  # noqa: BLE001 - no CUDA build, no GPU
            cuda = False
        root = (_models_dir / "whisper") if _models_dir else None
        try:
            model = WhisperModel(MODEL, device="cuda" if cuda else "cpu", compute_type="float16" if cuda else "int8",
                                 cpu_threads=os.cpu_count() or 4, download_root=str(root) if root else None)
        except Exception as exc:  # network errors, a hub outage
            raise ModelUnavailable(
                "Couldn’t download the lyrics model (Whisper) from Hugging Face. Connect to the internet and try "
                f"again; it’s downloaded only once. ({type(exc).__name__}: {str(exc)[:200]})"
            ) from exc
        _cache[MODEL] = model
        marker = _marker()
        if marker:
            marker.write_text("ok\n")
        return model


def download() -> None:
    """Fetch the model ahead of time (Profile); progress and errors show in :func:`status`."""
    if _download["active"]:
        return
    _download.update(active=True, error=None)

    def run():
        try:
            load()
        except Exception as exc:  # noqa: BLE001 - reported through status()
            _download["error"] = str(exc)
        finally:
            _download["active"] = False

    threading.Thread(target=run, name="download-whisper", daemon=True).start()


def transcribe(y: np.ndarray, progress: Callable[[float], None] | None = None,
               should_stop: Callable[[], bool] | None = None,
               on_download: Callable[[], None] | None = None) -> dict:
    """Every sung word in ``y`` (mono, 16 kHz), with its times: ``{"language", "words"}``."""
    model = load(on_download)
    duration = max(1e-6, y.size / SR)
    segments, info = model.transcribe(
        np.ascontiguousarray(y, dtype=np.float32), word_timestamps=True, beam_size=5,
        # Music has long stretches without words: skip them. Each line is read in the light of the
        # one before (Whisper's default), which is where its punctuation, and so the lines, come from.
        vad_filter=True,
    )
    words = []
    for seg in segments:
        if should_stop and should_stop():
            raise Cancelled()
        if progress:
            progress(min(1.0, seg.end / duration))
        if HALLUCINATIONS.search(seg.text) or (seg.no_speech_prob > 0.6 and seg.avg_logprob < -1.0):
            continue
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append({"start": round(float(w.start), 2), "end": round(float(w.end), 2), "text": text})
    return {"language": info.language, "words": words}


# ------------------------------------------------------------------ lines


def split_lines(words: list[dict]) -> list[dict]:
    """Words into sung lines: at a pause, at the end of a phrase, or after MAX_LINE_WORDS."""
    lines: list[list[dict]] = []
    for w in words:
        if lines:
            line = lines[-1]
            prev = line[-1]
            ends_phrase = re.search(r"[.!?]$", prev["text"]) or (
                re.search(r"[,;:]$", prev["text"]) and len(line) >= MIN_PHRASE_WORDS)
            gap = w["start"] - prev["end"]
            paused = gap >= LONG_GAP or (gap >= LINE_GAP and len(line) >= MIN_PHRASE_WORDS)
            if paused or ends_phrase or len(line) >= MAX_LINE_WORDS:
                lines.append([w])
                continue
            line.append(w)
        else:
            lines.append([w])
    return [_line(line) for line in lines]


def _line(words: list[dict]) -> dict:
    words = [dict(w) for w in words]
    # A line ends without its comma or full stop, as charts print it ("…nuestro Señor").
    words[-1]["text"] = re.sub(r"[,;:.]+$", "", words[-1]["text"]) or words[-1]["text"]
    return {"start": words[0]["start"], "end": words[-1]["end"], "words": words}


def spread(text: str, start: float, end: float) -> list[dict]:
    """A line's words across ``start``..``end`` by their length, when only the line has a time."""
    tokens = text.split()
    if not tokens:
        return []
    weights = np.array([len(t) + 2 for t in tokens], dtype=float)
    edges = start + (end - start) * np.concatenate([[0], np.cumsum(weights)]) / weights.sum()
    return [{"start": round(float(a), 2), "end": round(float(b), 2), "text": t}
            for t, a, b in zip(tokens, edges[:-1], edges[1:], strict=True)]


# ------------------------------------------------------------------ LRCLIB

_SUFFIX = re.compile(
    r"\s+(con letra|letra|en vivo|live|lyrics?|en hd|hd|4k|oficial|official|video|v[ií]deo|audio)\s*$", re.IGNORECASE)
_NOISE = re.compile(
    r"\s*[\(\[][^)\]]*\b(live|en vivo|vivo|letra|lyrics?|official|oficial|video|v[ií]deo|audio|hd|4k|cover|"
    r"versi[oó]n|version|remaster(ed)?|karaoke|instrumental|ft\.?|feat\.?|con letra)\b[^)\]]*[\)\]]",
    re.IGNORECASE,
)


def search_terms(title: str, artist: str = "") -> list[tuple[str, str]]:
    """The (track, artist) pairs to look a song up by, most likely first, from its title and artist.

    Video titles carry the artist and extras in the title ("YO TE BUSCO | STEPHANIE CALZADILLA |
    CENTRO VIDA", "Marco Barrientos - Los Carros Del Faraón (Letra)", "Renuévame by Marcos Witt
    con letra en HD"); LRCLIB wants them apart. "A - B" can be either way round, so both are tried.
    """
    track = _NOISE.sub("", title or "").strip()
    while _SUFFIX.search(track):
        track = _SUFFIX.sub("", track).strip()
    who = (artist or "").split("|")[0].strip()
    if "|" in track:
        parts = [p.strip() for p in track.split("|") if p.strip()]
        track = parts[0]
        who = who or (parts[1] if len(parts) > 1 else "")
    m = re.match(r"^(.+?)\s+by\s+(.+)$", track, flags=re.IGNORECASE)
    if m:
        track, who = m.group(1).strip(), who or m.group(2).strip()
    pairs = []
    if " - " in track:
        left, right = (p.strip() for p in track.split(" - ", 1))
        pairs += [(right, left), (left, right)] if not who else [(left, who), (right, left), (left, right)]
    else:
        pairs.append((track, who))
    out = []
    for t, a in pairs:
        t, a = t.strip(" -–|"), a.strip(" -–|")
        if t and (t, a) not in out:
            out.append((t, a))
    return out


def _get_json(url: str, timeout: float = 8.0):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Lrclib-Client": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as res:  # noqa: S310 - a fixed https host
        return json.loads(res.read().decode("utf-8"))


def normalize(text: str) -> str:
    """For comparing words and titles: lower case, no accents or punctuation."""
    text = unicodedata.normalize("NFKD", text.lower())
    return re.sub(r"[^a-z0-9ñ ]+", "", "".join(c for c in text if not unicodedata.combining(c))).strip()


def _similar(a: str, b: str) -> float:
    a, b = normalize(a), normalize(b)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _fits(rec: dict, track: str, duration: float | None) -> bool:
    """Whether an LRCLIB record can be this song: lyrics, a similar title, about as long."""
    return bool((rec.get("syncedLyrics") or rec.get("plainLyrics"))
                and _similar(rec.get("trackName") or "", track) >= 0.6
                and not (duration and rec.get("duration") and abs(float(rec["duration"]) - duration) > DURATION_SLACK))


def lookup(title: str, artist: str, duration: float | None,
           fetch: Callable[[str], object] | None = None) -> tuple[dict | None, str | None]:
    """The song's lyrics on LRCLIB: ``(record, None)``, or ``(None, why not)``."""
    fetch = fetch or _get_json
    pairs = search_terms(title, artist)
    if not pairs:
        return None, "the song has no title to look it up by"
    queries = []
    for track, who in pairs:
        if who:
            queries.append(({"track_name": track, "artist_name": who}, track, who))
    for track, who in pairs:
        queries.append(({"q": f"{track} {who}".strip()}, track, who))
    seen, candidates = set(), []  # (record, the track and artist it was found by)
    try:
        for q, track, who in queries:
            for rec in fetch(f"{LRCLIB}/api/search?{urllib.parse.urlencode(q)}") or []:
                if isinstance(rec, dict) and rec.get("id") not in seen and not rec.get("instrumental"):
                    seen.add(rec.get("id"))
                    candidates.append((rec, track, who))
            if any(_fits(rec, track, duration) and rec.get("syncedLyrics") for rec, track, _ in candidates):
                break
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None, "LRCLIB couldn’t be reached"

    def score(found: tuple) -> float:
        rec, track, who = found
        s = 2.0 * _similar(rec.get("trackName") or "", track)
        if who:
            s += _similar(rec.get("artistName") or "", who)
        if rec.get("syncedLyrics"):
            s += 1.0
        if duration and rec.get("duration"):
            s -= abs(float(rec["duration"]) - duration) / DURATION_SLACK
        return s

    fitting = [c for c in candidates if _fits(c[0], c[1], duration)]
    if not fitting:
        return None, "LRCLIB has no lyrics for this song"
    best = max(fitting, key=score)[0]
    return {
        "id": best.get("id"), "track": best.get("trackName"), "artist": best.get("artistName"),
        "synced": parse_lrc(best["syncedLyrics"]) if best.get("syncedLyrics") else None,
        "plain": [ln.strip() for ln in (best.get("plainLyrics") or "").splitlines() if ln.strip()],
    }, None


_TAG = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")


def parse_lrc(text: str) -> list[tuple[float, str]]:
    """``[mm:ss.xx] words`` lines into ``(seconds, words)``; empty lines mark breaks (``""``)."""
    out = []
    for raw in text.splitlines():
        tags = _TAG.findall(raw)
        words = _TAG.sub("", raw).strip()
        for m, s in tags:
            out.append((int(m) * 60 + float(s), words))
    return sorted(out, key=lambda x: x[0])


# ------------------------------------------------------------------ putting them together


def align(lines: list[tuple[float | None, str]], heard: list[dict], duration: float) -> tuple[list[dict], float]:
    """LRCLIB's lines (with their times, or None) timed word by word by Whisper's ``heard`` words.

    Returns the timed lines and the share of LRCLIB's words Whisper heard (how well they fit).
    A word Whisper didn't catch is placed between its neighbours; a line it missed altogether
    keeps its LRCLIB time, moved by how far LRCLIB's times are off in this recording.
    """
    tokens = [(i, t) for i, (_, text) in enumerate(lines) for t in text.split()]
    if not tokens:
        return [], 0.0
    ours = [normalize(t) for _, t in tokens]
    theirs = [normalize(w["text"]) for w in heard]
    times: list[tuple[float, float] | None] = [None] * len(tokens)
    for block in SequenceMatcher(None, ours, theirs, autojunk=False).get_matching_blocks():
        for k in range(block.size):
            w = heard[block.b + k]
            times[block.a + k] = (w["start"], w["end"])
    matched = sum(t is not None for t in times) / len(tokens)

    # How far LRCLIB's clock is from this recording's, from the lines whose first word was heard.
    offsets = []
    first = {}
    for k, (i, _) in enumerate(tokens):
        first.setdefault(i, k)
    for i, k in first.items():
        if lines[i][0] is not None and times[k] is not None:
            offsets.append(times[k][0] - lines[i][0])
    shift = float(np.median(offsets)) if offsets else 0.0

    out = []
    for i, (at, text) in enumerate(lines):
        ks = [k for k, (j, _) in enumerate(tokens) if j == i]
        known = [(k, times[k]) for k in ks if times[k] is not None]
        if not known:
            start = (at + shift) if at is not None else None
            if start is None:
                continue  # an untimed line Whisper never heard: nowhere to put it
            nxt = next((lines[j][0] + shift for j in range(i + 1, len(lines)) if lines[j][0] is not None), duration)
            words = spread(text, start, min(nxt - 0.1, start + 0.55 * len(ks) + 0.5))
        else:
            words = []
            for k in ks:
                if times[k] is not None:
                    a, b = times[k]
                else:  # between the nearest heard words of this line
                    before = [times[j] for j in ks if j < k and times[j] is not None]
                    after = [times[j] for j in ks if j > k and times[j] is not None]
                    a = before[-1][1] if before else max(0.0, after[0][0] - 0.4)
                    b = after[0][0] if after else a + 0.4
                    a, b = min(a, b), max(a, b)
                words.append({"start": round(a, 2), "end": round(b, 2), "text": tokens[k][1]})
        if words:
            out.append(_line(words))
    out.sort(key=lambda ln: ln["start"])
    return out, matched


def find(title: str, artist: str, duration: float, vocals: Callable[[], np.ndarray] | None, mode: str = "auto",
         progress: Callable[[float], None] | None = None, should_stop: Callable[[], bool] | None = None,
         on_download: Callable[[], None] | None = None,
         fetch: Callable[[str], object] | None = None) -> dict:
    """The song's lyrics, from LRCLIB and Whisper as ``mode`` allows.

    ``vocals`` gives the vocals (16 kHz mono) when Whisper is to listen. Returns
    ``{"source", "language", "lines", "lrclib"?, "note"?}``; ``lines`` is empty when none were found.
    """
    found, why = lookup(title, artist, duration, fetch) if mode in ("auto", "online") else (None, None)
    heard = None
    if mode == "auto" and vocals is not None and available():
        heard = transcribe(vocals(), progress, should_stop, on_download)
    credit = {"id": found["id"], "track": found["track"], "artist": found["artist"]} if found else None

    if found and heard is not None:
        lines = found["synced"] or [(None, text) for text in found["plain"]]
        timed, fit = align([(t, x) for t, x in lines if x], heard["words"], duration)
        if fit >= LRCLIB_MATCH and timed:
            return {"source": "lrclib", "language": heard["language"], "lines": timed, "lrclib": credit}
        why = "LRCLIB’s lyrics are of another version of this song"
    elif found and found["synced"]:
        synced = [(t, x) for t, x in found["synced"]]
        lines = []
        for k, (t, text) in enumerate(synced):
            if not text:
                continue
            nxt = next((u for u, _ in synced[k + 1:]), duration)
            words = spread(text, t, min(nxt - 0.1, t + 0.55 * len(text.split()) + 0.5))
            if words:
                lines.append(_line(words))
        return {"source": "lrclib", "language": None, "lines": lines, "lrclib": credit}
    if heard is not None and heard["words"]:
        out = {"source": "whisper", "language": heard["language"], "lines": split_lines(heard["words"])}
        if why:
            out["note"] = why
        return out
    if mode == "online" and found and not found["synced"]:
        why = "LRCLIB has these lyrics without times; turn on transcription to time them"
    return {"source": None, "language": None, "lines": [], "note": why or "no words were heard"}


def edit(lyrics: dict, texts: list[str]) -> dict:
    """Lyrics with each line's words replaced by ``texts[i]`` ("" removes the line).

    A line that keeps its number of words keeps their times; otherwise the new words are spread
    over the line's time.
    """
    lines = []
    for line, text in zip(lyrics["lines"], texts, strict=False):
        tokens = text.split()
        if not tokens:
            continue
        if len(tokens) == len(line["words"]):
            words = [{**w, "text": t} for w, t in zip(line["words"], tokens, strict=True)]
        else:
            words = spread(" ".join(tokens), line["start"], line["end"])
        lines.append({"start": line["start"], "end": line["end"], "words": words})
    return {**lyrics, "source": "edited",
            "edited_from": lyrics.get("edited_from") or lyrics.get("source"), "lines": lines}
