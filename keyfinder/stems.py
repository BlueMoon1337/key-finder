"""What a stem is, from its name: the rules Player (github.com/BlueMoon1337/Player) imports by.

Player brings in MultiTracks.com downloads (``Title-Album-Key-BPMbpm.zip`` holding
``MultiTracks/*.wav``), folders of stems, and its own song folders. These are the same rules in
Python, so KeyFinder recognizes the same packages and the same parts: a Click Track, a Guide,
the original mix for reference, and each instrument by the bus Playback would route it to.
KeyFinder's own stems are named by these rules too, so Player routes them the same way.
"""

from __future__ import annotations

import re

AUDIO_EXTENSIONS = ("wav", "wave", "bwf", "rf64", "aif", "aiff", "flac", "mp3", "m4a", "aac", "ogg", "oga", "opus")
_AUDIO = re.compile(r"\.(" + "|".join(AUDIO_EXTENSIONS) + r")$", re.IGNORECASE)

# Player's buses (src/audio/routing.ts), without the pad's, plus "reference" for the original
# mix (Player keeps that on its own, behind its Reference Track setting).
KINDS = ("click", "guide", "reference", "drums", "percussion", "loops", "bass", "piano", "keys", "eg", "ag",
         "strings", "horns", "vocals", "fx", "aux")
KIND_NAMES = {
    "click": "Click", "guide": "Guide", "reference": "Reference", "drums": "Drums", "percussion": "Percussion",
    "loops": "Loops", "bass": "Bass", "piano": "Piano", "keys": "Keys", "eg": "Electric Guitars",
    "ag": "Acoustic Guitars", "strings": "Strings", "horns": "Horns", "vocals": "Vocals", "fx": "FX", "aux": "Aux",
}
# Parts that aren't the music: KeyFinder leaves them out of the mix it analyses.
NOT_MUSIC = {"click", "guide", "reference"}
# Parts that carry the harmony: KeyFinder reads the key and chords from these.
HARMONIC = {"bass", "piano", "keys", "eg", "ag", "strings", "horns", "aux"}

# Playback's track names and buses, as Player lists them ("Name, 1-3" also means Name 1..3;
# "Name 1-3" only the numbered ones). Two differ from Player's list: the reference mix has its
# own kind, and the gayageum (a zither, which Playback sends to the click) counts as an instrument.
_DEFAULT_TRACKS = """
12 Strings: ag
Accordion, 1-2: aux
Acoustic Guitar, 1-3: ag
Acoustic Guitar Group: ag
Alto, 1-2: vocals
Arps, 1-2: keys
Aux Drums: percussion
Aux Drums (Live): percussion
Background Vocals, 1-6: vocals
Background Vocals FX, 1-4: fx
Bagpipes: aux
Band: aux
Banjo: aux
Banjo 1: ag
Banjo 2: aux
Bar Chimes: percussion
Baritone: vocals
Bass, 1-2: bass
Beatbox: loops
Bells: aux
Bongo: percussion
Bouzouki, 1-2: aux
Brass: horns
Brushes: percussion
Cajon: percussion
Cello, 1-3: strings
Chimes: aux
Choir, 1-3: vocals
Claps: loops
Clarinet, 1-3: aux
Clav: aux
Click Track: click
Congas: percussion
Cowbell: percussion
CP 70: keys
Crash Cymbals: percussion
Cuatro: ag
Daegeum: aux
Djembe: percussion
Dobro 1-3: aux
Double Bass, 1-3: strings
Drums, 1-2: drums
Drums (Live): drums
Dulcimer, 1-2: aux
EBow: aux
Electric Guitar, 1-12: eg
Electric Guitar Group, 1-2: eg
Electric Piano: piano
Fiddle: aux
Flute, 1-3: aux
French Horn, 1-3: horns
Full Score: aux
FX, 1-2: fx
Gayageum: aux
Glockenspiel: aux
Guide (Dynamic): guide
Guide (Non-Dynamic): guide
Guiro: percussion
Guitars: eg
Guzheng, 1-2: aux
Harmonica: aux
Harmonium: aux
Harp: strings
Horns, 1-2: horns
Janggu: aux
Keys, 1-10: keys
Keys Group: keys
Kids: vocals
Lap Steel, 1-2: aux
Lead Sheet: aux
Lead Vocal, 1-3: vocals
Left: aux
Loop, 1-4: loops
Lyre: strings
Mandolin, 1-2: aux
Marimba: aux
Master: aux
MD: guide
MD Custom: guide
MD My Voice: guide
Mellotron: keys
Name Your Track: aux
Oboe: aux
Oohs, 1-3: vocals
Orchestra: strings
Organ, 1-2: keys
Original Song (Cloud Song): aux
Original Song (Reference): reference
Perc (Live), 1-2: percussion
Percussion, 1-4: percussion
Piano, 1-3: piano
Piano FX: piano
Piri: aux
Rhodes: keys
Rhythm: aux
Right: aux
Rubab: aux
Saxophone, 1-3: horns
Sections: guide
Shaker: percussion
Sitar: aux
Sleigh Bells: percussion
Slide Guitar: eg
Snaps: loops
Soprano, 1-2: vocals
Spoken Word: aux
Steel Drums: percussion
Stereo Click + Tracks: aux
Stomps: percussion
Strings, 1-4: strings
Suspended Cymbals: percussion
Synth Bass, 1-2: bass
Synth Bells: keys
Synth FX: fx
Synth Group: keys
Synth Horns: keys
Synth Lead: keys
Synth Loop, 1-2: loops
Synth Pad: keys
Synth Strings: keys
Tambourine, 1-2: percussion
Tenor, 1-3: vocals
Theremin: keys
Timbales: percussion
Timpani: percussion
Toms: drums
Tracks: loops
Tremolo: aux
Trombone, 1-3: horns
Trumpet, 1-3: horns
Tuba, 1-3: horns
Turntables: loops
Ukulele, 1-2: aux
Upright Bass: bass
Vibes: aux
Viola, 1-3: strings
Violin, 1-3: strings
Vocal FX: fx
Vocal Loop: loops
Vocals: vocals
Vocoder: keys
VoxChop: fx
Whistle: aux
Woodwinds: aux
Wurli: keys
"""


def _defaults() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in _DEFAULT_TRACKS.strip().splitlines():
        names, kind = line.rsplit(":", 1)
        kind = kind.strip()
        m = re.match(r"^(.*?)(,)?\s+(\d+)-(\d+)$", names)
        if not m:
            out[names.lower()] = kind
            continue
        if m.group(2):
            out[m.group(1).lower()] = kind
        for n in range(int(m.group(3)), int(m.group(4)) + 1):
            out[f"{m.group(1)} {n}".lower()] = kind
    return out


DEFAULT_KINDS = _defaults()

# Names Playback doesn't list, by what they usually mean (MultiTracks' and others' shorthand).
_GUESSES = [
    (r"click|metronome", "click"),
    (r"guide|\bcues?\b|^md\b", "guide"),
    (r"\bfx\b|\bsfx\b|riser|sweep|impact", "fx"),
    (r"\b(ag|ags|acoustic|ac gtr|nylon)\b", "ag"),
    (r"\b(eg|egs|egtr|electric|e gtr|gtr|gtrs|guitar|guitars)\b", "eg"),
    (r"\b(bgv|bgvs|bv|bvs|vox|vocal|vocals|voc|choir|harmony|harmonies|lead|lv|alto|tenor|soprano)\b", "vocals"),
    (r"\b(bass|sub|808)\b", "bass"),
    (r"\b(piano|pno|grand)\b", "piano"),
    (r"\b(keys|key|kys|synth|synths|pad|pads|organ|rhodes|wurli|arp|arps|ep|b3)\b", "keys"),
    (r"\b(loop|loops|lp|program|programming|prog|beat|beats|electronic|sequence|seq)\b", "loops"),
    (r"\b(perc|percs|percussion|shaker|tamb|tambourine|conga|congas|bongo|bongos|cajon|timp|timpani|claps?)\b",
     "percussion"),
    (r"\b(drum|drums|dr|kit|kick|kik|snare|snr|hat|hats|hh|hihat|tom|toms|oh|overheads?|cymbals?|room)\b", "drums"),
    (r"\b(string|strings|str|violin|violins|viola|cello|celli|orch|orchestra)\b", "strings"),
    (r"\b(horn|horns|brass|sax|trumpet|tpt|trombone|tbn|tuba)\b", "horns"),
]


def is_reference_name(name: str) -> bool:
    """The original recording, kept for reference (Player's isReferenceName)."""
    return bool(re.match(r"^(ref|reference|reference mix|ref mix|original|original mix|full mix)( \d+)?$",
                         name.strip(), re.IGNORECASE))


def is_click_name(name: str) -> bool:
    """A stem that's the song's click (Player's isClickStem)."""
    return bool(re.match(r"^(click(\s*track)?|metronome)$", _AUDIO.sub("", name).strip(), re.IGNORECASE))


def kind_of(name: str) -> str:
    """What a stem is, by its name alone: one of KINDS."""
    k = re.sub(r"\s+", " ", _AUDIO.sub("", name).strip()).lower()
    if k in DEFAULT_KINDS:
        return DEFAULT_KINDS[k]
    # "Keys 11", "Drums (Studio)": as their plain name would go.
    plain = re.sub(r"[\s_-]*\d+$", "", re.sub(r"\s*\([^)]*\)\s*", " ", k)).strip()
    if plain in DEFAULT_KINDS:
        return DEFAULT_KINDS[plain]
    if is_reference_name(k):
        return "reference"
    words = re.sub(r"[_\-.]+", " ", plain)
    return next((kind for pattern, kind in _GUESSES if re.search(pattern, words)), "aux")


# ------------------------------------------------------------------ packages


def parse_song_name(raw: str) -> dict:
    """"Goodness of God-Victory-Ab-63.00bpm" → title, album (or artist), key and BPM."""
    name = re.sub(r"\.zip$", "", raw.strip(), flags=re.IGNORECASE).strip()
    m = re.match(r"^(.+?)-(.+)-([A-G](?:#|b)?m?)-(\d+(?:\.\d+)?)\s*bpm$", name, re.IGNORECASE)
    if not m:
        return {"title": name}
    bpm = float(m.group(4))
    key = m.group(3)[0].upper() + m.group(3)[1:]
    return {
        "title": m.group(1).strip(),
        "album": m.group(2).strip(),
        "key": key,
        "bpm": round(bpm, 2) if 20 <= bpm <= 400 else None,
    }


_PITCH = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def parse_key(key: str) -> tuple[int, str] | None:
    """"Ab" → (8, "major"), "F#m" → (6, "minor"); None if it isn't a key."""
    m = re.match(r"^\s*([A-Ga-g])([#b♯♭]?)\s*(m|min|minor|maj|major)?\s*$", key or "")
    if not m:
        return None
    tonic = _PITCH[m.group(1).upper()] + {"#": 1, "♯": 1, "b": -1, "♭": -1}.get(m.group(2), 0)
    mode = "minor" if (m.group(3) or "").lower() in ("m", "min", "minor") else "major"
    return tonic % 12, mode


def is_junk(path: str) -> bool:
    """Files a Mac or Ableton leaves around that aren't part of the song."""
    parts = path.replace("\\", "/").split("/")
    return any(p in ("__MACOSX", ".DS_Store") for p in parts) or parts[-1].startswith(".")


def is_audio(path: str) -> bool:
    return bool(_AUDIO.search(path))


def pick_files(paths: list[str]) -> dict:
    """The stems and the cover picture among the paths in a zip or folder (Player's pickFiles)."""
    files = [p.replace("\\", "/") for p in paths if not is_junk(p)]
    audio = [p for p in files if is_audio(p)]
    # A MultiTracks/ folder holds the stems; anything else (e.g. a preview MP3) is left out.
    in_folder = [p for p in audio if re.search(r"(^|/)multitracks/", p, re.IGNORECASE)]
    stems = sorted(in_folder or audio, key=str.lower)
    depth = lambda p: p.count("/")  # noqa: E731
    named = [p for p in files if re.search(r"(^|/)(album|artwork|cover|folder)\.(jpe?g|png)$", p, re.IGNORECASE)]
    shallow = [p for p in files if re.search(r"\.(jpe?g|png)$", p, re.IGNORECASE) and depth(p) <= 1]
    artwork = (sorted(named, key=depth) or sorted(shallow, key=depth) or [None])[0]
    return {"stems": stems, "artwork": artwork}


def _common_prefix(names: list[str]) -> str:
    if len(names) < 2:
        return ""
    p = names[0]
    for n in names:
        while not n.startswith(p):
            p = p[:-1]
    # Only keep it if it ends on a word boundary.
    return p if re.search(r"[\s_\-.]$", p) else ""


def display_names(file_names: list[str]) -> list[str]:
    """Each stem's name: its file name without the extension or the prefix they all share."""
    bases = [_AUDIO.sub("", n.rsplit("/", 1)[-1]) for n in file_names]
    prefix = _common_prefix(bases)
    return [(b[len(prefix):].lstrip(" _-.") or b).strip()[:40] for b in bases]


def stem_id(name: str, used: set[str]) -> str:
    """A stem's id in KeyFinder (its file name and URL): "EG 1" → "eg-1"."""
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "stem"
    if base == "original":
        base = "original-2"
    sid, n = base, 2
    while sid in used:
        sid, n = f"{base}-{n}", n + 1
    used.add(sid)
    return sid
