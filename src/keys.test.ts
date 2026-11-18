import { describe, expect, it } from 'vitest'
import { keyChart, keyInfo, parseKey } from './keys'

// The rows of the Major and Minor Keys and Scales charts (Keys.pdf, pages 1 and 2), in KeyFinder's
// spelling: ♯ and ♭ for # and b, "dim" right after the root.
const fix = (row: string) => row.replace(/#/g, '♯').replace(/b(?=\b|m|♯| |$)/g, '♭').replace(/ dim/g, 'dim').split(/\s+/)

const MAJOR = {
  sharps: [
    'C Dm Em F G Am B dim - 0',
    'G Am Bm C D Em F# dim - 1',
    'D Em F#m G A Bm C# dim - 2',
    'A Bm C#m D E F#m G# dim - 3',
    'E F#m G#m A B C#m D# dim - 4',
    'B C#m D#m E F# G#m A# dim - 5',
    'F# G#m A#m B C# D#m E# dim - 6',
    'C# D#m E#m F# G# A#m B# dim - 7',
  ],
  flats: [
    'F Gm Am Bb C Dm E dim - 1',
    'Bb Cm Dm Eb F Gm A dim - 2',
    'Eb Fm Gm Ab Bb Cm D dim - 3',
    'Ab Bbm Cm Db Eb Fm G dim - 4',
    'Db Ebm Fm Gb Ab Bbm C dim - 5',
    'Gb Abm Bbm Cb Db Ebm F dim - 6',
    'Cb Dbm Ebm Fb Gb Abm Bb dim - 7', // the chart has "Bbm" here; the seventh chord is B♭ diminished
  ],
}
const MINOR = {
  sharps: [
    'Am B dim C Dm Em F G - 0',
    'Em F# dim G Am Bm C D - 1',
    'Bm C# dim D Em F#m G A - 2',
    'F#m G# dim A Bm C#m D E - 3',
    'C#m D# dim E F#m G#m A B - 4',
    'G#m A# dim B C#m D#m E F# - 5',
    'D#m E# dim F# G#m A#m B C# - 6',
    'A#m B# dim C# D#m E#m F# G# - 7',
  ],
  flats: [
    'Dm E dim F Gm Am Bb C - 1',
    'Gm A dim Bb Cm Dm Eb F - 2',
    'Cm D dim Eb Fm Gm Ab Bb - 3',
    'Fm G dim Ab Bbm Cm Db Eb - 4',
    'Bbm C dim Db Ebm Fm Gb Ab - 5',
    'Ebm F dim Gb Abm Bbm Cb Db - 6',
    'Abm Bb dim Cb Dbm Ebm Fb Gb - 7',
  ],
}

describe('key chart', () => {
  for (const [mode, chart] of [['major', MAJOR], ['minor', MINOR]] as const) {
    for (const side of ['sharps', 'flats'] as const) {
      it(`matches the ${mode} keys with ${side}`, () => {
        const keys = keyChart(mode)[side]
        expect(keys.length).toBe(chart[side].length)
        keys.forEach((k, i) => {
          const [chords, count] = chart[side][i].split(' - ')
          expect(k.chords.map((c) => c.symbol)).toEqual(fix(chords))
          expect(k.count).toBe(Number(count))
          expect(k.sharps).toBe(side === 'sharps')
        })
      })
    }
  }

  it('spells scales by letter, and names numerals and relative keys', () => {
    expect(keyInfo('C♯', 'major').scale).toEqual(['C♯', 'D♯', 'E♯', 'F♯', 'G♯', 'A♯', 'B♯'])
    expect(keyInfo('C♭', 'major').scale).toEqual(['C♭', 'D♭', 'E♭', 'F♭', 'G♭', 'A♭', 'B♭'])
    expect(keyInfo('G', 'major').chords.map((c) => c.numeral)).toEqual(['I', 'ii', 'iii', 'IV', 'V', 'vi', 'vii°'])
    expect(keyInfo('A', 'minor').chords.map((c) => c.numeral)).toEqual(['i', 'ii°', 'III', 'iv', 'v', 'VI', 'VII'])
    expect(keyInfo('E♭', 'major').relative).toBe('C minor')
    expect(keyInfo('F♯', 'minor').relative).toBe('A major')
    expect(keyInfo('C♭', 'major').chords[3].rootPc).toBe(4) // F♭ sounds as E
  })

  it('reads key names', () => {
    expect(parseKey('F# minor')).toEqual({ pc: 6, mode: 'minor' })
    expect(parseKey('Db major')).toEqual({ pc: 1, mode: 'major' })
    expect(parseKey('')).toBeNull()
  })
})
