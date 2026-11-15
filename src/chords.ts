// Chord theory for the chord chart and the Chord Library: the chord types, their notes spelled as
// a musician would write them (E♭ minor seventh is E♭ G♭ B♭ D♭, not D♯ F♯ A♯ C♯), intervals,
// formulas and inversions, and a small piano-like sound to hear them by.

import type { Chord } from './api'
import { chordUsesFlats, mod12 } from './music'

export interface ChordType {
  id: string
  /** What follows the root in a chord symbol: "" for C, "m7" for Cm7. */
  suffix: string
  /** Its name in words, after the root: "minor seventh". */
  name: string
  group: 'Triads' | 'Sixths and sevenths' | 'Suspended' | 'Added and extended'
  /** Semitones above the root. */
  semitones: number[]
  /** The scale degree of each note, as a formula writes it ("1 ♭3 5 ♭7"). */
  degrees: string[]
}

const LETTERS = ['C', 'D', 'E', 'F', 'G', 'A', 'B']
const NATURAL = [0, 2, 4, 5, 7, 9, 11]
const MAJOR_DEGREE = [0, 2, 4, 5, 7, 9, 11] // semitones of degrees 1..7 in a major scale

function degreeSemitones(degree: string): number {
  const m = /^(𝄫|♭|♯)?(\d+)$/.exec(degree)!
  const n = Number(m[2])
  const base = MAJOR_DEGREE[(n - 1) % 7] + 12 * Math.floor((n - 1) / 7)
  return base + (m[1] === '♭' ? -1 : m[1] === '♯' ? 1 : m[1] === '𝄫' ? -2 : 0)
}

const t = (id: string, suffix: string, name: string, group: ChordType['group'], degrees: string) => {
  const ds = degrees.split(' ')
  return { id, suffix, name, group, degrees: ds, semitones: ds.map(degreeSemitones) }
}

/** Every chord type in the library; the first nine are the ones KeyFinder detects in songs. */
export const CHORD_TYPES: ChordType[] = [
  t('maj', '', 'major', 'Triads', '1 3 5'),
  t('min', 'm', 'minor', 'Triads', '1 ♭3 5'),
  t('7', '7', 'dominant seventh', 'Sixths and sevenths', '1 3 5 ♭7'),
  t('maj7', 'maj7', 'major seventh', 'Sixths and sevenths', '1 3 5 7'),
  t('min7', 'm7', 'minor seventh', 'Sixths and sevenths', '1 ♭3 5 ♭7'),
  t('dim', 'dim', 'diminished', 'Triads', '1 ♭3 ♭5'),
  t('aug', 'aug', 'augmented', 'Triads', '1 3 ♯5'),
  t('sus2', 'sus2', 'suspended second', 'Suspended', '1 2 5'),
  t('sus4', 'sus4', 'suspended fourth', 'Suspended', '1 4 5'),
  t('6', '6', 'sixth', 'Sixths and sevenths', '1 3 5 6'),
  t('m6', 'm6', 'minor sixth', 'Sixths and sevenths', '1 ♭3 5 6'),
  t('m7b5', 'm7♭5', 'half-diminished (minor seventh flat five)', 'Sixths and sevenths', '1 ♭3 ♭5 ♭7'),
  t('dim7', 'dim7', 'diminished seventh', 'Sixths and sevenths', '1 ♭3 ♭5 𝄫7'),
  t('mmaj7', 'm(maj7)', 'minor major seventh', 'Sixths and sevenths', '1 ♭3 5 7'),
  t('7sus4', '7sus4', 'dominant seventh suspended fourth', 'Suspended', '1 4 5 ♭7'),
  t('add9', 'add9', 'added ninth', 'Added and extended', '1 3 5 9'),
  t('madd9', 'm(add9)', 'minor added ninth', 'Added and extended', '1 ♭3 5 9'),
  t('9', '9', 'dominant ninth', 'Added and extended', '1 3 5 ♭7 9'),
  t('maj9', 'maj9', 'major ninth', 'Added and extended', '1 3 5 7 9'),
  t('m9', 'm9', 'minor ninth', 'Added and extended', '1 ♭3 5 ♭7 9'),
]
export const CHORD_GROUPS: ChordType['group'][] = ['Triads', 'Sixths and sevenths', 'Suspended', 'Added and extended']
export const typeById = (id: string) => CHORD_TYPES.find((c) => c.id === id)

/** The roots as the library offers them, spelled the common way (E♭ rather than D♯, F♯ rather than G♭). */
export const ROOTS = ['C', 'D♭', 'D', 'E♭', 'E', 'F', 'F♯', 'G', 'A♭', 'A', 'B♭', 'B']

/** A root's letter and pitch class from a name like "E♭" or "F♯" (or "Eb", "F#"). */
function parseRoot(name: string): { letter: number; pc: number } {
  const letter = LETTERS.indexOf(name[0].toUpperCase())
  const acc = name.slice(1).replace('b', '♭').replace('#', '♯')
  return { letter, pc: mod12(NATURAL[letter] + (acc === '♭' ? -1 : acc === '♯' ? 1 : 0)) }
}

/**
 * The chord's notes spelled from the root by degree: each note takes the letter its degree
 * calls for (a third is always a third letter up) and whatever sharp or flat makes the pitch.
 */
export function spell(root: string, type: ChordType): string[] {
  const r = parseRoot(root)
  return type.degrees.map((d, i) => {
    const n = Number(/(\d+)$/.exec(d)![1])
    const letter = (r.letter + n - 1) % 7
    const diff = mod12(r.pc + type.semitones[i] - NATURAL[letter])
    const acc = diff === 0 ? '' : diff === 1 ? '♯' : diff === 2 ? '𝄪' : diff === 11 ? '♭' : diff === 10 ? '𝄫' : '?'
    return LETTERS[letter] + acc
  })
}

/** The name to show for a root pitch class in a key that uses flats, or sharps. */
export function rootName(pc: number, flats: boolean) {
  return (flats ? ['C', 'D♭', 'D', 'E♭', 'E', 'F', 'G♭', 'G', 'A♭', 'A', 'B♭', 'B'] : ['C', 'C♯', 'D', 'D♯', 'E', 'F', 'F♯', 'G', 'G♯', 'A', 'A♯', 'B'])[mod12(pc)]
}

export const chordSymbol = (root: string, type: ChordType, bass?: string) => `${root}${type.suffix}${bass ? `/${bass}` : ''}`

/**
 * Keys to light on a keyboard starting at C: the chord in root position from the root in the
 * first octave, and its inversions (the lowest note moved up an octave each time).
 */
export function voicing(rootPc: number, type: ChordType, inversion = 0): number[] {
  const notes = type.semitones.map((s) => rootPc + s)
  for (let i = 0; i < inversion; i++) notes.push(notes.shift()! + 12)
  // Bring the lowest note into the first octave.
  const shift = Math.floor(Math.min(...notes) / 12) * 12
  return notes.map((n) => n - shift)
}

/**
 * A slash chord's keys: the bass in the first octave, the chord in root position above it.
 * Returns ``{ bass, chord, octaves }`` (how many octaves the keyboard needs).
 */
export function slashVoicing(rootPc: number, type: ChordType, bassPc: number) {
  let chord = voicing(rootPc, type)
  while (chord[0] <= bassPc) chord = chord.map((n) => n + 12)
  return { bass: bassPc, chord, octaves: Math.ceil((Math.max(...chord) + 1) / 12) }
}

/** How many inversions a chord has worth showing (one per note above the root, up to the seventh). */
export const inversionCount = (type: ChordType) => Math.min(type.semitones.length, 4) - 1

/** A detected chord (KeyFinder's quality names) as a library chord type, transposed. */
export function fromDetected(chord: Pick<Chord, 'root' | 'quality' | 'bass'>, shift: number, flats: boolean) {
  if (chord.root === null || chord.quality === null) return null
  const type = typeById(chord.quality)
  if (!type) return null
  const spelled = chordUsesFlats(chord.root + shift, chord.quality, flats)
  const root = rootName(chord.root + shift, spelled)
  const bass = chord.bass !== null && chord.bass !== undefined && mod12(chord.bass) !== mod12(chord.root)
    ? rootName(chord.bass + shift, spelled)
    : undefined
  return { root, rootPc: mod12(chord.root + shift), type, bass, bassPc: bass ? mod12(chord.bass! + shift) : undefined }
}

// ------------------------------------------------------------------ sound

let ctx: AudioContext | null = null

/**
 * Plays notes (semitones above middle C's octave start) with a soft, piano-like tone: all together,
 * one after another (``arpeggio``), or quickly from the lowest up, as a guitar's strum. A bass
 * note, if given, sounds an octave below.
 */
export function playChord(notes: number[], { arpeggio = false, strum = false, bass }: { arpeggio?: boolean; strum?: boolean; bass?: number } = {}) {
  ctx ??= new AudioContext()
  void ctx.resume()
  const now = ctx.currentTime + 0.02
  const out = ctx.createGain()
  out.gain.value = 0.22 / Math.sqrt(notes.length + (bass === undefined ? 0 : 1))
  out.connect(ctx.destination)
  const all = bass === undefined ? notes.map((n) => n + 48) : [bass + 36, ...notes.map((n) => n + 48)]
  all.forEach((midi, i) => {
    const start = now + i * (arpeggio ? 0.18 : strum ? 0.035 : 0.012)
    const f = 440 * 2 ** ((midi + 12 - 69) / 12) // the keyboard's first C is C4
    const env = ctx!.createGain()
    env.gain.setValueAtTime(0, start)
    env.gain.linearRampToValueAtTime(1, start + 0.008)
    env.gain.exponentialRampToValueAtTime(0.25, start + 0.4)
    env.gain.exponentialRampToValueAtTime(0.0001, start + 2.2)
    env.connect(out)
    for (const [mult, level, wave] of [[1, 1, 'triangle'], [2, 0.25, 'sine'], [3, 0.08, 'sine']] as const) {
      const osc = ctx!.createOscillator()
      osc.type = wave
      osc.frequency.value = f * mult
      const g = ctx!.createGain()
      g.gain.value = level
      osc.connect(g).connect(env)
      osc.start(start)
      osc.stop(start + 2.3)
    }
  })
}

/** Plays MIDI notes (a guitar shape's), strummed. */
export const playMidi = (midi: number[]) => playChord(midi.map((m) => m - 60), { strum: true })
