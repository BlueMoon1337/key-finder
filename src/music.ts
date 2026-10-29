// Key and chord names, transposed for the pitch control. Mirrors keyfinder/key.py and chords.py.

import type { Chord, Key } from './api'

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
export function chordLabel(chord: Pick<Chord, 'root' | 'quality' | 'bass'>, shift: number, flats: boolean) {
  if (chord.root === null || chord.quality === null) return 'N.C.'
  const names = flats ? FLAT : SHARP
  const name = names[mod12(chord.root + shift)] + (SUFFIX[chord.quality] ?? '')
  return chord.bass === null || chord.bass === undefined || mod12(chord.bass) === mod12(chord.root)
    ? name
    : `${name}/${names[mod12(chord.bass + shift)]}`
}

/** "Ab major" → "Ab major" moved by `shift` semitones, as the library shows it. */
export function transposeKeyName(key: Pick<Key, 'tonic' | 'mode'>, shift: number) {
  return keyName(key.tonic + shift, key.mode)
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
