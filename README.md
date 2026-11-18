<img src="build/icon.png" alt="KeyFinder icon" width="96">

# KeyFinder

A practice app for musicians, for macOS and Windows. Add a song and KeyFinder:

- **finds its key** (with the Camelot code, the relative key and how sure it is), **tempo**, beat grid and tuning, and **where the key or tempo changes** (medleys, a faster last song in a live set)
- **shows the chords** as the song plays, in three levels of detail: basic triads, sevenths, then dim, aug and sus
- **splits it into stems** with Demucs, Meta AI's neural separator: vocals, drums, bass and other; vocals and accompaniment; or six stems with guitar and piano. A mixer mutes, solos or turns down each one
- lets you **change the key** (±12 semitones, and the chords transpose with it) and the **speed** (50–150 %, without changing the pitch)
- has a **metronome that follows the song's own beats**, a one-bar **count-in** and **A–B loops** that snap to beats
- **transposes audio files** to another key (and speed) without adding them to the library (see [Transposing files](#transposing-files))
- **exports** your mix (the song without vocals, two semitones down at 80 %, say) as MP3, WAV or M4A
- **charts the song's chords** on piano keyboards, and has a **Chord Library** of every chord with its notes, intervals and inversions, and a **Keys** chart of the chords in every major and minor key (see [Chords](#chords))
- **shows the lyrics with the chords over the words**, following the song as it plays (see [Lyrics](#lyrics))
- **exports stems for [Player](https://github.com/BlueMoon1337/Player)**, the multitrack player: every stem, a click track on the song's own beats, the key and the tempo (see [Exporting for Player](#exporting-for-player))

## Using it

**Play** is your library: search it, filter it, sort it by when you added songs, title, artist, BPM or key. Click a song to open it. The **⋯** button (or a right-click) has Open, Edit Info, Download Original, Show in Finder / Explorer and Delete. While a song is loaded, the bar at the bottom plays and pauses it and skips between songs.

**+ Add** opens **Add a Song**:

| Source | Desktop app | In a browser |
| --- | --- | --- |
| **Import File** | Opens in Downloads | Any audio or video file |
| **Camera Roll** | Opens in Pictures, showing videos (Photos exports, phone imports) | Videos; on a phone, the photo library |
| **Music** | Opens in your Music library's media folder, showing songs | Audio files |
| **Cloud Storage** | A public Google Drive or Dropbox share link, or a direct link to a file. Streaming links (YouTube, Spotify…) won't work. | Same |
| **Stems** | A song that's already in stems: a MultiTracks.com zip, a folder of stems, or a song folder from Player's library. A Mac's dialog takes zips and folders; on Windows it picks folders, and zips come in through **Import File** (see [Songs in stems](#songs-in-stems)). | A zip of stems |

You can also drop files anywhere on the window, open them with KeyFinder from Finder or Explorer, or use **File ▸ Add a Song… (⌘N / Ctrl+N)** and **File ▸ Import File… (⌘O / Ctrl+O)**. Supported files: MP3, WAV, FLAC, M4A, AAC, AIFF, OGG, WMA, MP4, MOV and other video with an audio track.

In the player, **Space** plays and pauses, **← / →** move 5 seconds, **[ / ]** change the key, **L** turns the loop on and off and **M** the metronome. **⌘↑ / ⌘↓** (Ctrl on Windows) change the speed. Drag across the waveform to loop a section.

**Profile** shows library statistics, the defaults for new songs (how to split them, and the chord detail), the library folder, and updates.

### Chords

Under the chord timeline, **Chords** charts every chord in the song on a piano keyboard, with its notes, in the order they first come: in the key you're playing in (**Pitch**) and at the **Chords** detail you've chosen. The chord playing now is outlined. Click a chord to hear it; **▸ 0:22** goes to where it's first played, and **Library** opens it in the Chord Library. A slash chord shows its bass note in orange, under the chord. Chords heard for under two seconds in all (a passing bass note, a fill) wait behind **Show … brief chords**.

The **Chords** page (in the sidebar) is a chord reference, like muted.io's: pick a root and a type to see the chord on a keyboard with its notes spelled as charts write them (E♭m7 is E♭ G♭ B♭ D♭), its formula (1 ♭3 5 ♭7) and intervals, and its inversions, and to hear it, together or as an arpeggio. It has the nine chord types KeyFinder detects and eleven more (6, m6, m7♭5, dim7, m(maj7), 7sus4, add9, m(add9), 9, maj9, m9). Under **Guitar** it shows the chord's guitar shapes in standard tuning: the open shape where there is one (C = x32010), then barre shapes up the neck, each drawn with its finger numbers (the root's dots in orange), and strummed when you click it. KeyFinder works the shapes out rather than looking them up, so every chord and slash chord has them; they're kept to what a hand plays: a four-fret span, four fingers or a barre, no hand-crossing patterns. The song's **Chords** chart can draw guitar shapes too (**Piano / Guitar**). Chords your songs use carry an orange dot; each lists the songs it's in, and **Chords in your library** lists every chord KeyFinder has found in your songs, the most used first.

The **Keys** page (in the sidebar) charts the major and minor keys: for each key, the chord on each note of its scale (in a major key I, ii, iii, IV, V, vi, vii°: C Dm Em F G Am Bdim; in a minor key i, ii°, III, iv, v, VI, VII) and how many sharps or flats its signature has, the sharp keys (C to C♯, A minor to A♯ minor) and the flat keys (F to C♭, D minor to A♭ minor) in separate tables. Notes are spelled the way the key writes them, every letter once, so C♯ major's seventh chord is B♯dim and C♭ major's fourth is F♭. Click a chord to hear it; its key opens above the chart with its scale on a keyboard, its relative key, and each of its chords with a link to the Chord Library, which opens the chord spelled as the key spells it (B♯dim, not Cdim). Hover over a chord's name to see it: above the chart it lights the keyboard (with its notes and numeral), and in the chart it pops up beside the name (with its guitar shape too, when the chord view is **Guitar**). **Play the Scale** plays the scale up an octave and back down, showing the chord on each note as it sounds; **Play the Chords** plays those chords themselves, I to the octave and back (**Stop** ends either). The key of the song you're playing is marked ♪.

The **Circle** page (in the sidebar) is the circle of fifths: the twelve major keys round a wheel coloured from yellow C, a fifth apart (a sharp more each step clockwise, a flat more each step anticlockwise, meeting at the bottom where B is C♭, F♯ is G♭ and D♭ is C♯), with each one's relative minor in the ring outside it (Am by C, Em by G, G♯m and A♭m by B and C♭). Inside the circle is how many sharps or flats each key has; outside, its key signature on a staff (two at the bottom). Hover over a key, major or minor, to see its sharps or flats in the middle of the circle (D major: F♯ C♯), lit on its staff. Click a key, a name or a signature to open it and hear it: it opens beside the circle with the same keyboard, scale and chords as the Keys page (the two pages share the key you have open).

### Transposing files

**Transpose** (in the sidebar) changes the key of audio files, and their speed if you like, and saves them, without adding them to your library: for a singer's key, a guitar part without a capo, or a backing track. Add files with **Add Files…** or drop them on the page (several at once). KeyFinder finds each one's key and tempo first (the same analysis songs get, without separating stems), so you pick the new key by name ("C minor → D minor (+2)"), up to an octave either way. **Listen** renders it to hear first; **Save…** saves it as MP3, WAV, M4A or FLAC, named with its new key ("Song (D minor).mp3", "Song (D minor, 90%).mp3" at another speed); **Save All** saves every file into one folder. Video files work too: their sound is saved. Files are forgotten a day after they're added.

The pitch is shifted as the player's **Pitch** is: with Rubber Band (which keeps a voice's character) when a system FFmpeg has it, otherwise FFmpeg's resampling, which moves the voice's formants with it, so a big shift of a vocal sounds less natural.

### Lyrics

After a song is ready, KeyFinder finds its lyrics and shows them under the chords as a chart: each chord over the word it changes on, the line being sung bright and kept in view, its words lighting up as they're sung, and the chord playing now highlighted. Intros, solos and outros show their chords on a row of their own. Click a line to go there. The chords follow **Pitch** and the **Chords** detail, like the rest of the player.

The words come from two places:

- **LRCLIB** ([lrclib.net](https://lrclib.net)), a free database of song lyrics, many with a time for each line. KeyFinder looks the song up by its title, artist and length, and sends nothing else. A video's title is cleaned up first ("YO TE BUSCO | STEPHANIE CALZADILLA | CENTRO VIDA" → *Yo Te Busco* by *Stephanie Calzadilla*; "… (Letra)", "con letra en HD" and the like are dropped).
- **Whisper** (OpenAI's speech recognition, through faster-whisper), on this computer: it listens to the vocals stem (a package's lead vocal stem, or the whole song when it wasn't split) and writes down every word with its time. Its model (`large-v3-turbo`, about 1.6 GB) is downloaded once, the first time it's needed, or from **Profile ▸ Lyrics**. Allow a minute or two per song on Apple silicon, longer on Intel Macs and Windows.

With both, LRCLIB's words (spelled right) are timed by what Whisper heard, word by word; and if they don't match what's sung (LRCLIB has the studio version, you added a live one), Whisper's own words are used. Whisper can mishear a word (Moises' "Pondadoso" for "Bondadoso"): **Edit** corrects the lyrics line by line, keeping their timing. **Find again** looks them up again.

**Profile ▸ New songs ▸ Lyrics** chooses what happens for new songs: **Look up online, else transcribe** (the default), **Look up online only** (no Whisper, so no model download; LRCLIB's line times, with the words spread across each line), or **Off**. Songs added before lyrics existed have a **Find Lyrics** button.

### Tempo changes

A song that changes tempo partway through (a medley, a live set that moves into a faster song) gets a **tempo section** for each tempo, as a song that changes key gets key sections. The Tempo card shows the tempo at the playhead, with "tempo 2 of 3, then 120 at 4:02"; the library shows the first tempo with "+1"; the count-in counts at the tempo where you start; the metronome follows the beats, so it changes with them. In a Player export, each tempo change is a section ("120 BPM", or "C minor · 120 BPM" when the key changes with it).

What counts as a change:

- **At least 10 % and 30 seconds.** A band pushing a few percent, a ritardando at the end, or a pianist's rubato stays one tempo; the beats follow them anyway.
- **Confirmed by the kick and bass.** A hi-hat or shaker pattern can pulse at another tempo for minutes (in *Este Corito Es* the hats run at 100 over a band at 126), so a new tempo counts only where the low end plays it too.
- **Not the same beat counted differently.** Half time and double time aren't changes. A dotted-eighth guitar delay or a triplet feel pulses at 4:3 or 3:2 of the tempo and can sound like a new one, so a new tempo also has to be in the low end (kick and bass) before it counts. A real change from 90 to 120 is; a delay over a steady groove isn't.

Each tempo after the first is counted the way the one before it was: a song KeyFinder counts at 63 (half of 126) that moves into a song at 112 reads 63 → 56, a slowdown, as it is. ½× / 2× changes every section together.

With a Click Track, the click decides: a new tempo is wherever its clicks settle into a different spacing (10 % or more, for 30 seconds).

### Songs in stems

KeyFinder recognizes stems the way [Player](https://github.com/BlueMoon1337/Player) does, so anything Player imports, KeyFinder imports too. Add a zip or folder with **Stems**, drop it on the window, or use **Import File** for a zip:

| What | What KeyFinder takes from it |
| --- | --- |
| **MultiTracks.com zips** (`Goodness of God-Victory-Ab-63.00bpm.zip`) and the folders they unzip to | The title, key and tempo from the name; the WAVs in `MultiTracks/` as the stems; `Album.jpg` as the cover. |
| **Player song folders** (`Documents/Player Library/Songs/…`) | The title, artist, key and tempo from its `song.json`, its stems by their names in Player, and the stem Player uses as the click. |
| **KeyFinder's own Player exports** | Everything they went out with: the artist, the stems, the Click Track, and the Reference mix as the original. |
| **Any folder or zip of audio files** | Each file a stem, named after the file (a prefix they all share, like `My Song - `, is dropped). |

Nothing is separated: the stems are used as they are. Each one is sorted by name into the parts Player's buses use (Click, Guide, Drums, Percussion, Loops, Bass, Piano, Keys, Electric and Acoustic Guitars, Strings, Horns, Vocals, FX), with Playback's list of track names and the shorthand MultiTracks uses (`EG 1`, `BGVs`, `Synth Pad`, `MD`). The mixer lists them in that order, and says what a stem is when its name doesn't.

The analysis uses the parts:

- **Beats and bars** come from the **Click Track** when there is one: every click a beat, and the accented clicks the first beat of each bar (4/4, 3/4 or 6/8 alike). Where the click stops, KeyFinder carries on at the tempo it had, and where the click changes tempo, so does the song (see [Tempo changes](#tempo-changes)).
- **Key and chords** come from the instruments that carry the harmony (bass, keys, piano, guitars, strings, horns), not the drums, vocals, click or guide. A key the package names (MultiTracks' name, Player's song) is kept; key changes inside it are still found.
- **Tempo:** the name's BPM, when the beats agree with it (the beat tracker's ½× or 2× is corrected to it).
- **The original** is the package's reference mix (`Reference`, `Original`, `Full Mix`) when it has one; otherwise the stems mixed, without the click and guide.

Zips imported from disk in the desktop app can be up to 8 GB; uploads in a browser are limited to 500 MB (`KEYFINDER_MAX_UPLOAD_MB`).

### Exporting for Player

In the player's **Practice** panel, choose **Stems for Player** and **Export Stems…**. KeyFinder writes a zip laid out like a MultiTracks.com download, which Player imports as one song (drop it on Player's window, or **File ▸ Import Songs…**):

| In the zip | What Player does with it |
| --- | --- |
| Its name, `Title-Artist-Key-BPMbpm.zip` (e.g. `Yo Venceré-Danilo Montero-Cm-156.00bpm.zip`) | Title, artist, key and tempo. Keep the name as it is: it's the only place Player reads the key from. The artist goes where MultiTracks put the album; Player knows it's a KeyFinder export by the WAVs' software tag and reads it as the artist. |
| `MultiTracks/Vocals.wav`, `Drums.wav`, `Bass.wav`… | One channel per stem, each on its bus (vocals, drums, bass, piano, guitar). A song that came in stems keeps its stems' names (`EG 1`, `BGVs`, `Guide`). |
| `MultiTracks/Click Track.wav` | The song's click, on the beats KeyFinder found, accented on each bar. It follows a live performance's tempo, which a click from one BPM can't. It goes to Player's Click bus. A song that came with its own click sends that one. |
| `MultiTracks/Reference.wav` | The original mix, for Player's **Reference Track** setting. |
| Tags in each WAV | Title and artist, "KeyFinder" as the software, the tempo and 4/4, and for a song that changes key or tempo, a section at each change ("D minor", "120 BPM", "C minor · 120 BPM"). |
| A beat map in each WAV (a `bmap` chunk) | Where bar 1 falls, every tempo change and every change in bar length, which Player lists in **Song Settings ▸ Tempo Changes** and **Time Changes**. Its click, bar lines, jumps at the next bar and count-ins follow them. |
| `Album.jpg` | The cover. |

The beat map is finer than the [tempo sections](#tempo-changes): it's read from the beats as they were tracked (in each tempo section at its own tempo), and records every move of more than 3 % that stays for eight beats, so Player's click follows a band that settles a little faster after a bridge, while a live performance's drift stays one tempo. A bar runs from one downbeat to the next, so a bar stretched or cut short where the downbeats shift is a time signature change of its own, as the click plays it. The player's **Tempo** figure counts these changes (when the song has no tempo sections, which it shows instead) and the bar lengths, and lists each one when you point at it.

The `bmap` chunk is JSON, with times in seconds: `{"version": 1, "offset": 0.52, "tempos": [[0, 156.0], [95.3, 150.2]], "meters": [[0, 4, 4], [61.0, 2, 4]]}`.

The export uses the pitch and speed you hear, so a song exported two semitones down at 90 % arrives in Player in its new key and tempo. The mixer's levels don't apply: Player mixes the stems itself. The stems are 16-bit WAVs, about 10 MB a minute each.

The library lives in `Documents/KeyFinder Library`: one folder per song, with its stems, analysis and artwork.

## Installing

Download the latest release from the [Releases page](https://github.com/BlueMoon1337/key-finder/releases/latest):

- **macOS:** `KeyFinder-…-arm64-mac.dmg` for Apple silicon, `…-x64-mac.dmg` for Intel. Drag KeyFinder to Applications.
- **Windows:** `KeyFinder-Setup-….exe`.

The apps aren't signed with an Apple Developer ID or a Windows certificate (macOS builds are ad-hoc signed), so the first time:

- **macOS:** right-click KeyFinder and choose **Open**, or use **System Settings ▸ Privacy & Security ▸ Open Anyway**.
- **Windows:** in the SmartScreen box, choose **More info ▸ Run anyway**.

To give KeyFinder to someone, or put it on another computer, use **File ▸ Save a Copy of KeyFinder…** (or **Profile ▸ Share KeyFinder**). On a Mac it saves a disk image (`.dmg`, with the usual drag-to-Applications window) or a `.zip` of the app; on Windows, a `.zip` of the installed app, which runs from wherever it's unzipped (open `KeyFinder.exe`). The copy is the app only, about 400 MB: not your library, settings, update token or downloaded models. It's for the same kind of computer it was saved on (Apple silicon or Intel, Windows) and needs the same first-time right-click ▸ Open or More info ▸ Run anyway as a download.

After that, **Profile ▸ Updates** installs new versions by itself (see [Releases](#releases-and-updates)).

## How it's built

| Part | What it is |
| --- | --- |
| `electron/` | The desktop app's main process. Its window, menus, IPC trust check, window-state memory, single-instance lock, updater and release scripts come from [Player](https://github.com/BlueMoon1337/Player). |
| `src/` | The interface: React and TypeScript, built with Vite. It runs in the desktop app or a browser (`src/platform` hides the difference, as in Player). |
| `keyfinder/` | The analysis engine, in Python. The desktop app runs it as a child process (`keyfinder/engine.py`) that listens on 127.0.0.1 and answers only requests carrying a token made for that launch. The app adds the token as it passes requests through its `app://keyfinder/api` protocol, so nothing else on the computer can use the engine. |
| `packaging/` | Freezes the engine, Demucs, PyTorch and Whisper included, with PyInstaller, so the app needs no Python. Audio goes through PyAV (FFmpeg's libraries), so no FFmpeg install is needed either. |

How the analysis works:

| Feature | Method |
| --- | --- |
| Key | Tuning-corrected chroma correlated with Krumhansl–Kessler and Temperley key profiles. Relative major/minor ties are broken with the chord sequence (time on the tonic chord, the first and last chord). |
| Tempo and beats | Spectral-flux onsets → prior-weighted autocorrelation → Ellis's dynamic-programming beat tracker; downbeats from low-frequency accents. The tempo is read from the whole mix and its low end (kick and bass) together, so a pattern only the hi-hats play can't pass for the beat. Tempo changes: the tempo in 12-second windows, octave-folded and smoothed with a Viterbi pass, and the beats tracked section by section (above). |
| Chords | Beat-synchronous chroma and bass chroma, template matching against the chord vocabulary, a key-aware prior, and Viterbi smoothing weighted by duration. |
| Stems | [Demucs](https://github.com/adefossez/demucs) (Hybrid Transformer Demucs: `htdemucs`, and `htdemucs_6s` for six stems), run in the engine's process (`keyfinder/neural.py`). The fallback is a fast DSP separator (harmonic/percussive median filtering, stereo centre extraction, crossovers) that gives stems adding back up to the mix. |
| Pitch | Rendered by the engine and cached: Rubber Band (formant-preserving) when a system FFmpeg has it, else FFmpeg's `asetrate` + `atempo`. |
| Speed | Live in the player (`playbackRate` with the pitch kept). |

### Stem separation with Demucs

The desktop app separates stems with Demucs, which comes bundled with PyTorch.

- **Where it runs.** It uses the GPU on Apple silicon Macs (Metal), an NVIDIA GPU when PyTorch has CUDA (from source), and the CPU otherwise (Windows, Intel Macs). On the CPU, allow a few minutes per song. Set `KEYFINDER_DEVICE` (`cpu`, `mps`, `cuda`) to choose.
- **Models.** The weights aren't in the installer. Each model is downloaded once from the Hugging Face hub (`adefossez/HTDemucs`, `adefossez/HTDemucs-6s`) the first time a song needs it, or ahead of time with **Profile ▸ Stem separation ▸ Download**. They're kept in KeyFinder's settings folder (`~/Library/Application Support/KeyFinder/models` on a Mac, `%APPDATA%\KeyFinder\models` on Windows), and separation works offline after that. Downloads come from `huggingface.co` and its file CDN (`*.hf.co`, e.g. `us.aws.cdn.hf.co`), so a firewall must allow both.
- **Offline the first time.** If a model can't be downloaded and the engine is set to **Best available**, the song is separated with the fast separator instead, and the mixer says so. With **Demucs** chosen, the song fails with the reason.
- **Better quality.** `KEYFINDER_DEMUCS_MODEL=htdemucs_ft` uses Demucs' fine-tuned model for 2 and 4 stems. It's a little better and about four times slower.
- **Intel Macs** get PyTorch 2.2, the last version built for them (Demucs selects it).

Choosing **Fast (DSP)** in Profile skips Demucs. It takes seconds and is good for turning a part down to play along, but it doesn't isolate parts cleanly.

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

On Windows the virtual environment's Python is `.venv\Scripts\python.exe`. For Demucs and lyrics transcription, also run `pip install -e ".[ml]"`. On Linux, install CPU-only PyTorch first unless you have an NVIDIA GPU (`pip install torch --index-url https://download.pytorch.org/whl/cpu`); PyPI's Linux PyTorch includes several gigabytes of CUDA libraries.

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

This works the same way as Player's. The **Release** workflow (`.github/workflows/release.yml`) builds KeyFinder for Apple silicon Macs, Intel Macs and Windows, signs the update files and publishes a GitHub release.

Apple silicon builds run on GitHub's Apple silicon runner (`macos-latest`); they don't use `macos-15-intel`. That runner builds only the Intel Mac version. Removing its entry from the workflow drops the Intel build and leaves Apple silicon builds unaffected.

To publish a release:

1. Raise `version` in `package.json` (and in `pyproject.toml` and `keyfinder/__init__.py`).
2. Push to `main`. The workflow starts by itself when that version hasn't been released. Pushing a `v…` tag, or **Actions ▸ Release ▸ Run workflow**, also starts it.

It needs the repository secret **`UPDATE_SIGNING_KEY`** (**Settings ▸ Secrets and variables ▸ Actions**). KeyFinder uses the same signing key pair as Player (`electron/update-key.pem` is Player's public key), so paste the same private key you use for Player. Updates are signed over "KeyFinder update", so a Player update can never be installed as a KeyFinder one. Without the secret the installers are still released, but with no update files, so the Update button doesn't offer that version.

In the app, **Profile ▸ Updates** asks once for a fine-grained GitHub token with **Contents: Read-only** on this repository, since it's private. KeyFinder then checks for new releases at start-up and every six hours, and **Install and Restart** downloads the update, checks its signature, replaces the app and opens it again.

### Update packages and going back

When the Update button can't be used (no token, no network, or the Release workflow couldn't run), KeyFinder can be updated from a zip: **Profile ▸ Updates ▸ Install from Zip…**. It takes:

- an **update package**, made with `npm run update-package` (→ `release/KeyFinder-<version>-update.zip`; releases attach one too). It carries the interface (`app.asar`) and `keyfinder-update.json` with its version and checksum, so one package fits every Mac and Windows: the analysis engine already installed is kept. Use it when the engine hasn't changed since the installed version. With `UPDATE_SIGNING_KEY` set the package is signed, and KeyFinder shows it as signed; otherwise it warns that it isn't.
- a release's **app zip** (`KeyFinder-<version>-arm64-mac.zip` / `-x64-mac.zip`): the whole app, engine included. It must be built for the Mac's processor.
- on Windows, a zip containing the release's **installer**.

KeyFinder checks the zip before installing anything: it must be KeyFinder, at a version it can read, for this computer, and match its checksum and (when it has one) its signature. Anything else is refused with **Zip File Invalid** and the reason. A package that isn't signed, or that's older than or the same as the version you have, is installed only with **Install Anyway**.

Every update (from a package or from the Update button) first keeps the version it replaces in KeyFinder's settings folder (`versions/`). **Go Back to …** in **Profile ▸ Updates** puts it back, and keeps the version you went back from, so you can switch again. Updates and going back change only the app: the library (`Documents/KeyFinder Library`) and the settings stay as they are. The swap happens after KeyFinder quits, in a small script that keeps what's there until the new version is in place, then opens KeyFinder again and reports how it went.

KeyFinder before 1.3.2 has no Install from Zip. Every package also carries `install-on-mac.sh`, which installs it on a Mac by hand (`bash ~/Downloads/KeyFinder-<version>-update/install-on-mac.sh`) and keeps the replaced version for Go Back the same way.

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
| `GET` | `/api/songs/{id}/export?semitones=&speed=&format=player` | the stems package for Player (a zip) |
| `POST` | `/api/songs/{id}/lyrics` | find the lyrics again (`{"mode": "auto"}` or `"online"`) |
| `PUT` | `/api/songs/{id}/lyrics` | correct the lyrics (`{"lines": ["…", "…"]}`, one string per line; `""` removes it) |
| `POST` | `/api/lyrics/download` | download the Whisper model ahead of time |
| `POST` | `/api/transpose` | add a file to transpose (`file`); returns its key, keys and tempo |
| `POST` | `/api/transpose/local` | desktop only: add files to transpose by path (`{"paths": […]}`) |
| `GET` | `/api/transpose/{id}/render?semitones=&speed=&format=` | the file in its new key and speed (`mp3`, `wav`, `m4a` or `flac`) |
| `DELETE` | `/api/transpose/{id}` | forget a file |
| `GET` | `/api/songs/{id}/export/player-name?semitones=&speed=` | the package's file name |
