# KeyFinder

A self-hosted practice tool for musicians. Upload a song and KeyFinder will:

- **Detect the key** (with Camelot code, relative key and confidence), **tempo/beat grid** and **tuning offset**
- **Detect chords** synced to playback, at three detail levels (basic triads → 7ths → dim/aug/sus)
- **Separate stems**: vocals / drums / bass / other (or vocals + accompaniment, or 6 stems with guitar and piano)
- Let you **practice** with a per-stem mixer (volume, mute, solo), **pitch shift** (±12 semitones, chords
  transpose with it), **speed control** without pitch change, a **smart metronome** that follows the
  song's detected beats, a one-bar **count-in**, and **A–B looping** snapped to beats
- **Export** your custom mix (e.g. the song without vocals, down 2 semitones, at 80% speed) as MP3, WAV or M4A

## Quick start

Requires Python 3.10+ and [ffmpeg](https://ffmpeg.org/) on your `PATH`.

```bash
python -m venv .venv
.venv/bin/pip install -e .
.venv/bin/keyfinder serve        # http://127.0.0.1:8000
```

For studio-quality stems install the neural separator (pulls in PyTorch, a large download):

```bash
.venv/bin/pip install -e ".[ml]"
```

Without it, stems come from a fast built-in DSP separator (harmonic/percussive median filtering, stereo
centre extraction and frequency crossovers). It's good enough to turn the drums or vocals down for
practice, but you won't get clean isolation.

### Command line

```bash
keyfinder analyze song.mp3 --chords            # key, BPM, tuning and the chord timeline
keyfinder analyze *.mp3 --json                 # machine-readable
keyfinder separate song.mp3 --mode 4stems --out stems/
```

## How it works

| Feature | Method |
| --- | --- |
| Key | Tuning-corrected chroma, correlated with Krumhansl–Kessler and Temperley key profiles; relative major/minor ties are broken using the chord sequence (tonic dwell time, first and last chord) |
| Tempo & beats | Spectral-flux onset envelope → prior-weighted autocorrelation tempo estimate → Ellis dynamic-programming beat tracker; downbeats from low-frequency accents |
| Chords | Beat-synchronous chroma + bass chroma, cosine template matching against the chord vocabulary, key-aware prior, Viterbi smoothing with duration-weighted evidence |
| Stems | [Demucs](https://github.com/facebookresearch/demucs) (`htdemucs` / `htdemucs_6s`) when installed, else the DSP separator; both produce stems that sum to the mix |
| Pitch shift | ffmpeg `rubberband` (formant-preserving) rendered server-side and cached; `asetrate`+`atempo` fallback |
| Speed | Browser `playbackRate` with `preservesPitch`, so it changes instantly |

## API

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/api/capabilities` | available separation backends and modes |
| `GET` | `/api/songs` | library |
| `POST` | `/api/songs` | multipart: `file`, `mode` (`2stems`/`4stems`/`6stems`/`none`), `backend` (`auto`/`demucs`/`dsp`) |
| `GET` | `/api/songs/{id}` | status, progress and full analysis |
| `DELETE` | `/api/songs/{id}` | |
| `GET` | `/api/songs/{id}/stems/{stem}?semitones=n` | stem audio, optionally transposed |
| `GET` | `/api/songs/{id}/export?semitones=&speed=&volumes=vocals:0,drums:0.5&format=mp3` | rendered mixdown |

Songs are stored under `./data` (set `KEYFINDER_DATA` or `--data` to change it). The upload limit is 200 MB
(`KEYFINDER_MAX_UPLOAD_MB`).

## Development

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/ruff check .
```

The tests synthesise chord progressions, click tracks and stereo mixes, so they need no audio fixtures.
