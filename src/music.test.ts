import { describe, expect, it } from 'vitest'
import { beatIndexAt, camelot, chordIndexAt, chordLabel, formatTime, keyName, keySortValue, keyUsesFlats, relativeKey } from './music'

describe('keys', () => {
  it('names keys with conventional spellings', () => {
    expect(keyName(1, 'major')).toBe('Db major')
    expect(keyName(1, 'minor')).toBe('C# minor')
    expect(keyName(-1, 'major')).toBe('B major')
    expect(keyName(13, 'minor')).toBe('C# minor')
  })

  it('matches the Camelot wheel', () => {
    expect(camelot(0, 'major')).toBe('8B')
    expect(camelot(9, 'minor')).toBe('8A')
    expect(camelot(4, 'major')).toBe('12B')
    expect(camelot(6, 'major')).toBe('2B')
    expect(camelot(3, 'minor')).toBe('2A')
  })

  it('finds relative keys and flat signatures', () => {
    expect(relativeKey(0, 'major')).toBe('A minor')
    expect(relativeKey(9, 'minor')).toBe('C major')
    expect(keyUsesFlats(5, 'major')).toBe(true)
    expect(keyUsesFlats(7, 'major')).toBe(false)
    expect(keyUsesFlats(2, 'minor')).toBe(true)
  })

  it('sorts keys chromatically, major before minor', () => {
    const keys = ['D major', 'C minor', 'Bb major', 'C major', 'C# minor', undefined]
    expect([...keys].sort((a, b) => keySortValue(a) - keySortValue(b))).toEqual([
      'C major',
      'C minor',
      'C# minor',
      'D major',
      'Bb major',
      undefined,
    ])
  })
})

describe('chords', () => {
  it('transposes and spells chords', () => {
    expect(chordLabel({ root: 9, quality: 'min' }, 0, false)).toBe('Am')
    expect(chordLabel({ root: 9, quality: 'min' }, 2, false)).toBe('Bm')
    expect(chordLabel({ root: 7, quality: '7' }, 3, true)).toBe('Bb7')
    expect(chordLabel({ root: 7, quality: '7' }, 3, false)).toBe('A#7')
    expect(chordLabel({ root: null, quality: null }, 3, false)).toBe('N.C.')
  })

  it('finds the chord and beat at a time', () => {
    const chords = [
      { start: 0, end: 2, root: 0, quality: 'maj', label: 'C' },
      { start: 2, end: 4, root: 7, quality: 'maj', label: 'G' },
    ]
    expect(chordIndexAt(chords, 0)).toBe(0)
    expect(chordIndexAt(chords, 2)).toBe(1)
    expect(chordIndexAt(chords, 5)).toBe(-1)
    expect(beatIndexAt([0.5, 1, 1.5], 0.2)).toBe(-1)
    expect(beatIndexAt([0.5, 1, 1.5], 1)).toBe(1)
    expect(beatIndexAt([0.5, 1, 1.5], 9)).toBe(2)
  })

  it('formats times', () => {
    expect(formatTime(0)).toBe('0:00')
    expect(formatTime(61.9)).toBe('1:01')
    expect(formatTime(Number.NaN)).toBe('0:00')
  })
})
