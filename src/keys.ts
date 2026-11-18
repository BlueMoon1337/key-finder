// The keys and their chords, as a reference chart: for each major and minor key, its scale
// spelled by letter (C♯ major's seventh note is B♯, C♭ major's fourth is F♭), its key signature,
// and the triad built on each note of the scale.

import { CHORD_TYPES, type ChordType, spellScale } from './chords'
import { mod12 } from './music'

export type Mode = 'major' | 'minor'

export interface DiatonicChord {
  /** The scale degree, 1 to 7. */
  degree: number
  root: string
  rootPc: number
  type: ChordType
  /** As a chord chart writes it: "F♯m", "B♯dim". */
  symbol: string
  /** As a Roman numeral: "ii", "vii°". */
  numeral: string
}

export interface KeyInfo {
  tonic: string
  tonicPc: number
  mode: Mode
  /** "C♯ major". */
  name: string
  /** The scale, from the tonic, spelled by letter. */
  scale: string[]
  /** How many sharps (or flats) the key signature has. */
  count: number
  /** Whether the signature is sharps; a key with none counts as a sharp key, as charts list it. */
  sharps: boolean
  chords: DiatonicChord[]
  /** The major or minor key with the same signature. */
  relative: string
}

const STEPS: Record<Mode, number[]> = {
  major: [0, 2, 4, 5, 7, 9, 11],
  minor: [0, 2, 3, 5, 7, 8, 10], // natural minor
}
const QUALITIES: Record<Mode, ChordType['id'][]> = {
  major: ['maj', 'min', 'min', 'maj', 'maj', 'min', 'dim'],
  minor: ['min', 'dim', 'maj', 'min', 'min', 'maj', 'maj'],
}
const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII']

/** The keys in chart order: no accidentals, then one sharp to seven, and one flat to seven. */
export const KEY_TONICS: Record<Mode, { sharps: string[]; flats: string[] }> = {
  major: { sharps: ['C', 'G', 'D', 'A', 'E', 'B', 'F♯', 'C♯'], flats: ['F', 'B♭', 'E♭', 'A♭', 'D♭', 'G♭', 'C♭'] },
  minor: { sharps: ['A', 'E', 'B', 'F♯', 'C♯', 'G♯', 'D♯', 'A♯'], flats: ['D', 'G', 'C', 'F', 'B♭', 'E♭', 'A♭'] },
}

/** What each column of the chart holds: "1 – Major", "2 – minor", "7 – dim". */
export const DEGREE_HEADINGS: Record<Mode, string[]> = {
  major: QUALITIES.major.map((q, i) => `${i + 1} – ${q === 'maj' ? 'Major' : q === 'min' ? 'minor' : 'dim'}`),
  minor: QUALITIES.minor.map((q, i) => `${i + 1} – ${q === 'maj' ? 'Major' : q === 'min' ? 'minor' : 'dim'}`),
}

const typeOf = (id: string) => CHORD_TYPES.find((t) => t.id === id)!

export function keyInfo(tonic: string, mode: Mode): KeyInfo {
  const scale = spellScale(tonic, STEPS[mode])
  const tonicPc = pcOf(tonic)
  const sharp = scale.filter((n) => n.includes('♯')).length
  const flat = scale.filter((n) => n.includes('♭')).length
  const chords = scale.map((root, i): DiatonicChord => {
    const type = typeOf(QUALITIES[mode][i])
    const roman = type.id === 'maj' ? ROMAN[i] : ROMAN[i].toLowerCase()
    return {
      degree: i + 1,
      root,
      rootPc: mod12(tonicPc + STEPS[mode][i]),
      type,
      symbol: root + type.suffix,
      numeral: type.id === 'dim' ? `${roman}°` : roman,
    }
  })
  // The relative key: a major key's sixth note, a minor key's third.
  const relative = mode === 'major' ? `${scale[5]} minor` : `${scale[2]} major`
  return { tonic, tonicPc, mode, name: `${tonic} ${mode}`, scale, count: Math.max(sharp, flat), sharps: flat === 0, chords, relative }
}

/** Every key of a mode, as the chart lists them. */
export function keyChart(mode: Mode) {
  return { sharps: KEY_TONICS[mode].sharps.map((t) => keyInfo(t, mode)), flats: KEY_TONICS[mode].flats.map((t) => keyInfo(t, mode)) }
}

const LETTER_PC: Record<string, number> = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 }

/** A note's pitch class from its name: "C♯", "B♭", "Cb", "E#". */
export function pcOf(name: string) {
  const acc = name.slice(1).replace(/#/g, '♯').replace(/b/g, '♭')
  return mod12(LETTER_PC[name[0].toUpperCase()] + [...acc].reduce((n, a) => n + (a === '♯' ? 1 : a === '♭' ? -1 : 0), 0))
}

/** A key's name ("F# minor", "Db major") as its tonic's pitch class and mode, or null. */
export function parseKey(name: string | undefined | null): { pc: number; mode: Mode } | null {
  const m = /^([A-G][#b♯♭]?)\s*(major|minor)/i.exec(name ?? '')
  return m ? { pc: pcOf(m[1]), mode: m[2].toLowerCase() as Mode } : null
}
