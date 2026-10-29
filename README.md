<img src="build/icon.png" alt="KeyFinder icon" width="96">

# KeyFinder

A practice app for musicians, for macOS and Windows. Add a song and KeyFinder:

- **finds its key** (with the Camelot code, the relative key and how sure it is), **tempo**, beat grid and tuning
- **shows the chords** as the song plays, in three levels of detail: basic triads, sevenths, then dim, aug and sus
- **splits it into stems** (vocals, drums, bass and other; or vocals and accompaniment) with a mixer to mute, solo or turn down each one
- lets you **change the key** (±12 semitones, and the chords transpose with it) and the **speed** (50–150 %, without changing the pitch)
- has a **metronome that follows the song's own beats**, a one-bar **count-in** and **A–B loops** that snap to beats
- **exports** your mix (the song without vocals, two semitones down at 80 %, say) as MP3, WAV or M4A

## Using it

**Play** is your library: search it, filter it, sort it by when you added songs, title, artist, BPM or key. Click a song to open it. The **⋯** button (or a right-click) has Open, Edit Info, Download Original, Show in Finder / Explorer and Delete. While a song is loaded, the bar at the bottom plays and pauses it and skips between songs.

**+ Add** opens **Add a Song**:

| Source | Desktop app | In a browser |
| --- | --- | --- |
| **Import File** | Opens in Downloads | Any audio or video file |
| **Camera Roll** | Opens in Pictures, showing videos (Photos exports, phone imports) | Videos; on a phone, the photo library |
| **Music** | Opens in your Music library's media folder, showing songs | Audio files |
| **Cloud Storage** | A public Google Drive or Dropbox share link, or a direct link to a file. Streaming links (YouTube, Spotify…) won't work. | Same |

You can also drop files anywhere on the window, open them with KeyFinder from Finder or Explorer, or use **File ▸ Add a Song… (⌘N / Ctrl+N)** and **File ▸ Import File… (⌘O / Ctrl+O)**. Supported files: MP3, WAV, FLAC, M4A, AAC, AIFF, OGG, WMA, MP4, MOV and other video with an audio track.

In the player, **Space** plays and pauses, **← / →** move 5 seconds, **[ / ]** change the key, **L** turns the loop on and off and **M** the metronome. **⌘↑ / ⌘↓** (Ctrl on Windows) change the speed. Drag across the waveform to loop a section.

**Profile** shows library statistics, the defaults for new songs (how to split them, and the chord detail), the library folder, and updates.

The library lives in `Documents/KeyFinder Library`: one folder per song, with its stems, analysis and artwork.

## Installing

Download the latest release from GitHub:

- **macOS:** `KeyFinder-…-arm64-mac.dmg` for Apple silicon, `…-x64-mac.dmg` for Intel. Drag KeyFinder to Applications.
- **Windows:** `KeyFinder-Setup-….exe`.

The apps aren't signed with an Apple Developer ID or a Windows certificate (macOS builds are ad-hoc signed), so the first time:

- **macOS:** right-click KeyFinder and choose **Open**, or use **System Settings ▸ Privacy & Security ▸ Open Anyway**.
- **Windows:** in the SmartScreen box, choose **More info ▸ Run anyway**.

After that, **Profile ▸ Updates** installs new versions by itself (see [Releases](#releases-and-updates)).

## How it's built

| Part | What it is |
| --- | --- |
| `electron/` | The desktop app's main process. Its window, menus, IPC trust check, window-state memory, single-instance lock, updater and release scripts come from [Player](https://github.com/BlueMoon1337/Player). |
| `src/` | The interface: React and TypeScript, built with Vite. It runs in the desktop app or a browser (`src/platform` hides the difference, as in Player). |
| `keyfinder/` | The analysis engine, in Python. The desktop app runs it as a child process (`keyfinder/engine.py`) that listens on 127.0.0.1 and answers only requests carrying a token made for that launch. The app adds the token as it passes requests through its `app://keyfinder/api` protocol, so nothing else on the computer can use the engine. |
| `packaging/` | Freezes the engine with PyInstaller so the app needs no Python. Audio goes through PyAV (FFmpeg's libraries), so no FFmpeg install is needed either. |

How the analysis works:

| Feature | Method |
| --- | --- |
| Key | Tuning-corrected chroma correlated with Krumhansl–Kessler and Temperley key profiles. Relative major/minor ties are broken with the chord sequence (time on the tonic chord, the first and last chord). |
| Tempo and beats | Spectral-flux onsets → prior-weighted autocorrelation → Ellis's dynamic-programming beat tracker; downbeats from low-frequency accents. |
| Chords | Beat-synchronous chroma and bass chroma, template matching against the chord vocabulary, a key-aware prior, and Viterbi smoothing weighted by duration. |
| Stems | [Demucs](https://github.com/facebookresearch/demucs) (`htdemucs`, `htdemucs_6s`) when it's installed; otherwise a fast DSP separator (harmonic/percussive median filtering, stereo centre extraction, crossovers). Both give stems that add back up to the mix. |
| Pitch | Rendered by the engine and cached: Rubber Band (formant-preserving) when a system FFmpeg has it, else FFmpeg's `asetrate` + `atempo`. |
| Speed | Live in the player (`playbackRate` with the pitch kept). |

**Stem quality.** The desktop app ships with the fast DSP separator. It's good for turning a part down to play along, but it won't isolate parts cleanly. Demucs gives studio-quality stems, but it needs PyTorch (about 2 GB), so it isn't bundled. Run KeyFinder from source with `pip install -e ".[ml]"` to use it, and 6-stem separation becomes available.

## Running from source

You need Python 3.10+ and Node.js 20+.

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
npm install
```

```bash
npm run dev        # the desktop app, reloading as you edit; it runs the engine from .venv
```

```bash
npm run dev:web    # the same interface in a browser at http://localhost:5173
```

On Windows the virtual environment's Python is `.venv\Scripts\python.exe`. Add `".[ml]"` to the pip install for Demucs.

The engine also works on its own:

```bash
.venv/bin/keyfinder analyze song.mp3 --chords     # key, BPM, tuning and the chord timeline
.venv/bin/keyfinder separate song.mp3 --out stems/
.venv/bin/keyfinder serve                         # the web app on http://127.0.0.1:8000 (after npm run build)
```

### Building the app

```bash
.venv/bin/pip install -e ".[desktop]"   # PyInstaller
npm run engine                          # freeze the engine → build/engine-dist/
npm run dist:mac -- --arm64             # or --x64; or: npm run dist:win
```

Installers land in `release/`. Each build is for the computer it's made on, because the engine inside is native code, so build Mac apps on a Mac and Windows apps on Windows. The release workflow does this for you.

### Tests

```bash
.venv/bin/pytest          # engine: synthesised chord progressions, click tracks and mixes, the API
.venv/bin/ruff check .
npm run typecheck
npm test                  # interface helpers (Vitest)
```

The **CI** workflow runs all of them on every push and pull request.

## Releases and updates

This works the same way as Player's. The **Release** workflow (`.github/workflows/release.yml`) builds KeyFinder for Apple silicon Macs, Intel Macs and Windows, signs the update files and publishes a GitHub release:

1. Raise `version` in `package.json` (and in `pyproject.toml` and `keyfinder/__init__.py`).
2. Push to `main`. The workflow starts by itself when that version hasn't been released. Pushing a `v…` tag, or **Actions ▸ Release ▸ Run workflow**, also starts it.

It needs the repository secret **`UPDATE_SIGNING_KEY`** (**Settings ▸ Secrets and variables ▸ Actions**). KeyFinder uses the same signing key pair as Player (`electron/update-key.pem` is Player's public key), so paste the same private key you use for Player. Updates are signed over "KeyFinder update", so a Player update can never be installed as a KeyFinder one. Until the secret exists, the workflow does nothing and says why.

In the app, **Profile ▸ Updates** asks once for a fine-grained GitHub token with **Contents: Read-only** on this repository, since it's private. KeyFinder then checks for new releases at start-up and every six hours, and **Install and Restart** downloads the update, checks its signature, replaces the app and opens it again.

## API

The engine's HTTP API, used by the interface:

| Method | Path | |
| --- | --- | --- |
| `GET` | `/api/capabilities` | separation engines and modes |
| `GET` / `POST` | `/api/songs` | the library; add a song by upload (`file`, `mode`, `backend`) |
| `POST` | `/api/songs/url` | add a song from a link (public addresses only) |
| `POST` | `/api/songs/local` | desktop app only: add songs by path |
| `GET` / `PATCH` / `DELETE` | `/api/songs/{id}` | a song with its analysis; edit its title and artist; delete it |
| `GET` | `/api/songs/{id}/cover` | its artwork |
| `GET` | `/api/songs/{id}/stems/{stem}?semitones=n` | a stem, optionally in another key |
| `GET` | `/api/songs/{id}/export?semitones=&speed=&volumes=vocals:0,drums:0.5&format=mp3` | a rendered mix |
