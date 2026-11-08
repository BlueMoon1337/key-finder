// Key and chord names, transposed for the pitch control. Mirrors keyfinder/key.py and chords.py.

import type { Chord, Key, LyricLine } from './api'

const SHARP = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
const FLAT = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B']
// Conventional tonic spellings: Db major rather than C# major, but C# minor.
const MAJOR_TONIC = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']
const MINOR_TONIC = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'G#', 'A', 'Bb', 'B']
const FLAT_MAJOR = new Set([1, 3, 5, 8, 10])
const FLAT_MINOR = new Set([0, 2, 3, 5, 7, 10])
const SUFFIX: Record<string, string> = {
  maj: '',
  min: 'm',
  '7': '7',
  maj7: 'maj7',
  min7: 'm7',
  dim: 'dim',
  aug: 'aug',
  sus2: 'sus2',
  sus4: 'sus4',
}

export const mod12 = (n: number) => ((n % 12) + 12) % 12

/** Player's bus order, which the mixer lists stems in, and each kind's short name. */
export const STEM_KINDS: [string, string][] = [
  ['click', 'Click'], ['guide', 'Guide'], ['drums', 'Drums'], ['percussion', 'Perc'], ['loops', 'Loops'],
  ['bass', 'Bass'], ['piano', 'Piano'], ['keys', 'Keys'], ['eg', 'EG'], ['ag', 'AG'], ['strings', 'Strings'],
  ['horns', 'Horns'], ['vocals', 'Vocals'], ['fx', 'FX'], ['aux', 'Aux'], ['reference', 'Ref'],
]

/** Stem ids in Player's bus order; stems of one kind keep their order (EG 1 before EG 2). */
export function orderStems(ids: string[], kinds: Record<string, string>) {
  const rank = (id: string) => {
    const i = STEM_KINDS.findIndex(([k]) => k === kinds[id])
    return i < 0 ? STEM_KINDS.length : i
  }
  return ids.map((id, i) => ({ id, i })).sort((a, b) => rank(a.id) - rank(b.id) || a.i - b.i).map((x) => x.id)
}

export function keyName(tonic: number, mode: Key['mode']) {
  return `${(mode === 'major' ? MAJOR_TONIC : MINOR_TONIC)[mod12(tonic)]} ${mode}`
}

export function keyUsesFlats(tonic: number, mode: Key['mode']) {
  return (mode === 'major' ? FLAT_MAJOR : FLAT_MINOR).has(mod12(tonic))
}

/** Camelot wheel code used by DJs: C major = 8B, A minor = 8A. */
export function camelot(tonic: number, mode: Key['mode']) {
  const relMajor = mode === 'major' ? mod12(tonic) : mod12(tonic + 3)
  return `${(8 + 7 * relMajor) % 12 || 12}${mode === 'major' ? 'B' : 'A'}`
}

export function relativeKey(tonic: number, mode: Key['mode']) {
  return mode === 'major' ? keyName(tonic + 9, 'minor') : keyName(tonic + 3, 'major')
}

/** A chord's name after transposing by `shift` semitones (G/B for an inversion); "N.C." for no chord. */
const MINORISH = new Set(['min', 'min7', 'dim', 'dim7', 'm7b5', 'm6', 'mmaj7', 'madd9', 'm9'])

/**
 * Whether to spell a chord's root with flats. Mostly the key's choice, but not where that gives
 * a chord nobody writes: G♭ minor (G♭ B𝄫 D♭) is F♯m, D♭ minor is C♯m; D♯ and A♯ major are E♭ and B♭.
 */
export function chordUsesFlats(root: number, quality: string, flats: boolean) {
  const r = mod12(root)
  if (flats && MINORISH.has(quality) && (r === 1 || r === 6)) return false
  if (!flats && !MINORISH.has(quality) && (r === 3 || r === 10)) return true
  return flats
}

export function chordLabel(chord: Pick<Chord, 'root' | 'quality' | 'bass'>, shift: number, flats: boolean) {
  if (chord.root === null || chord.quality === null) return 'N.C.'
  const names = chordUsesFlats(chord.root + shift, chord.quality, flats) ? FLAT : SHARP
  const name = names[mod12(chord.root + shift)] + (SUFFIX[chord.quality] ?? '')
  return chord.bass === null || chord.bass === undefined || mod12(chord.bass) === mod12(chord.root)
    ? name
    : `${name}/${names[mod12(chord.bass + shift)]}`
}

/** "Ab major" → "Ab major" moved by `shift` semitones, as the library shows it. */
export function transposeKeyName(key: Pick<Key, 'tonic' | 'mode'>, shift: number) {
  return keyName(key.tonic + shift, key.mode)
}

/** The key section playing at `t` (the first or last one outside them); null without sections. */
export function keySectionAt<T extends { start: number; end: number }>(sections: T[] | undefined, t: number): T | null {
  if (!sections?.length) return null
  for (const s of sections) if (t >= s.start && t < s.end) return s
  return t < sections[0].start ? sections[0] : sections[sections.length - 1]
}

/** Index of the chord playing at `t`, or -1 (binary search; chords are in order and contiguous). */
export function chordIndexAt(chords: Chord[], t: number) {
  let lo = 0
  let hi = chords.length - 1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (chords[mid].end <= t) lo = mid + 1
    else if (chords[mid].start > t) hi = mid - 1
    else return mid
  }
  return -1
}

/** Index of the last beat at or before `t`, or -1. */
export function beatIndexAt(beats: number[], t: number) {
  let lo = 0
  let hi = beats.length
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (beats[mid] <= t) lo = mid + 1
    else hi = mid
  }
  return lo - 1
}

/**
 * Which beat of its bar `t` falls on (0 for the downbeat), or -1 before the first beat.
 * Counted from the latest downbeat, because the bar's phase can shift between sections.
 */
export function beatInBar(beats: number[], downbeats: number[], t: number, beatsPerBar = 4) {
  const b = beatIndexAt(beats, t)
  if (b < 0) return -1
  const d = beatIndexAt(downbeats, beats[b] + 1e-6)
  if (d < 0) {
    // Before the first downbeat: count back from it.
    const first = beats.indexOf(downbeats[0])
    return first < 0 ? mod12(b) % beatsPerBar : (((b - first) % beatsPerBar) + beatsPerBar) % beatsPerBar
  }
  const start = beats.indexOf(downbeats[d])
  // A bar stretched where the phase shifts stays on its last beat rather than starting a new bar.
  return start < 0 ? 0 : Math.min(b - start, beatsPerBar - 1)
}

export function formatTime(s: number) {
  if (!Number.isFinite(s) || s < 0) s = 0
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`
}

/** Sort order for keys in the library: C, C#/Db, D … with major before minor. */
export function keySortValue(name: string | undefined) {
  if (!name) return 99
  const [tonic, mode] = name.split(' ')
  const pc = Math.max(SHARP.indexOf(tonic), FLAT.indexOf(tonic))
  return pc < 0 ? 98 : pc * 2 + (mode === 'minor' ? 1 : 0)
}

/** A word of a lyric line with the chords that change on it (in order). */
export interface PlacedWord {
  text: string
  start: number
  end: number
  chords: Chord[]
}

export type LyricRow =
  | { kind: 'line'; index: number; start: number; end: number; words: PlacedWord[] }
  /** A stretch without words (intro, solo, outro): its chords on their own. */
  | { kind: 'break'; start: number; end: number; chords: Chord[] }

/** A pause between lines this long, with chords in it, gets a row of its own. */
const BREAK_SECONDS = 4
/** A chord this close before a word belongs to it (players change a hair early). */
const EARLY = 0.35

/**
 * The lyrics laid out as a chart: each chord over the word being sung when it changes, the chord
 * already playing over a line's first word, and the chords of an intro, a solo or an outro on
 * rows of their own. Chords in a short pause go over the last word before it.
 */
export function placeChords(lines: LyricLine[], chords: Chord[]): LyricRow[] {
  const real = chords.filter((c) => c.root !== null)
  const rows: LyricRow[] = []
  const used = new Set<Chord>()
  const breakRow = (from: number, to: number) => {
    const inside = real.filter((c) => c.start >= from && c.start < to && !used.has(c))
    inside.forEach((c) => used.add(c))
    if (inside.length) rows.push({ kind: 'break', start: from, end: to, chords: inside })
  }
  if (lines.length && lines[0].start >= BREAK_SECONDS) breakRow(0, lines[0].start - EARLY)
  lines.forEach((line, i) => {
    const next = lines[i + 1]?.start ?? Infinity
    const longPause = next - line.end >= BREAK_SECONDS
    // Chords from just before the line to its end, or on to the next line if the pause is short.
    const until = longPause ? line.end + 0.5 : next - EARLY
    const words: PlacedWord[] = line.words.map((w) => ({ ...w, chords: [] }))
    for (const c of real) {
      if (used.has(c) || c.start < line.start - EARLY || c.start >= until) continue
      let k = 0
      while (k + 1 < words.length && words[k + 1].start <= c.start + EARLY) k++
      words[k].chords.push(c)
      used.add(c)
    }
    if (words.length && !words[0].chords.length) {
      const playing = real.find((c) => c.start <= line.start && c.end > line.start)
      if (playing) words[0].chords.unshift(playing)
    }
    rows.push({ kind: 'line', index: i, start: line.start, end: line.end, words })
    if (longPause) breakRow(line.end + 0.5, Number.isFinite(next) ? next - EARLY : Infinity)
  })
  return rows
}

/** Index of the line being sung at `t` (the last one started), or -1 before the first. */
export function lineIndexAt(lines: LyricLine[], t: number) {
  let found = -1
  for (let i = 0; i < lines.length && lines[i].start <= t + 0.15; i++) found = i
  return found
}
