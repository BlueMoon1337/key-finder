import { describe, expect, it } from 'vitest'
import type { Chord } from './api'
import { beatIndexAt, beatInBar, lineIndexAt, orderStems, placeChords, camelot, keySectionAt, chordIndexAt, chordLabel, formatTime, keyName, keySortValue, keyUsesFlats, relativeKey } from './music'

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
    expect(chordLabel({ root: 7, quality: '7' }, 3, false)).toBe('Bb7') // A#7 would be A# C## E# G#
    expect(chordLabel({ root: 7, quality: '7' }, 1, false)).toBe('G#7')
    expect(chordLabel({ root: null, quality: null }, 3, false)).toBe('N.C.')
    // Inversions keep their bass note through transposition.
    expect(chordLabel({ root: 7, quality: 'maj', bass: 11 }, 0, false)).toBe('G/B')
    expect(chordLabel({ root: 7, quality: 'maj', bass: 11 }, 2, false)).toBe('A/C#')
    expect(chordLabel({ root: 7, quality: 'maj', bass: 11 }, 3, true)).toBe('Bb/D')
    expect(chordLabel({ root: 7, quality: 'maj', bass: null }, 0, false)).toBe('G')
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

  it('counts beats from the latest downbeat, even when the bar shifts', () => {
    const beats = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    // Bars start at 1 and 5, then a section shifts the bar so it starts at 10.
    const downbeats = [1, 5, 10]
    expect(beatInBar(beats, downbeats, 0)).toBe(3) // the pickup before the first bar
    expect(beatInBar(beats, downbeats, 1)).toBe(0)
    expect(beatInBar(beats, downbeats, 7.5)).toBe(2)
    expect(beatInBar(beats, downbeats, 9)).toBe(3) // beat 5 of a stretched bar stays on the last dot
    expect(beatInBar(beats, downbeats, 10)).toBe(0)
    expect(beatInBar(beats, downbeats, 11.2)).toBe(1)
    expect(beatInBar(beats, downbeats, -1)).toBe(-1)
  })

  it('finds the key section at a time', () => {
    const sections = [
      { start: 0, end: 160, name: 'D minor' },
      { start: 160, end: 245, name: 'C minor' },
      { start: 245, end: 485, name: 'E minor' },
    ]
    expect(keySectionAt(sections, 10)?.name).toBe('D minor')
    expect(keySectionAt(sections, 160)?.name).toBe('C minor')
    expect(keySectionAt(sections, 999)?.name).toBe('E minor')
    expect(keySectionAt([], 3)).toBeNull()
    expect(keySectionAt(undefined, 3)).toBeNull()
  })

  it('formats times', () => {
    expect(formatTime(0)).toBe('0:00')
    expect(formatTime(61.9)).toBe('1:01')
    expect(formatTime(Number.NaN)).toBe('0:00')
  })
})

describe('orderStems', () => {
  it('lists stems in Player\'s bus order, keeping each kind\'s own order', () => {
    const kinds = { 'eg-2': 'eg', keys: 'keys', 'click-track': 'click', 'eg-1': 'eg', bgvs: 'vocals', drums: 'drums', odd: 'mystery' }
    expect(orderStems(['eg-2', 'keys', 'click-track', 'eg-1', 'bgvs', 'drums', 'odd'], kinds)).toEqual([
      'click-track', 'drums', 'keys', 'eg-2', 'eg-1', 'bgvs', 'odd',
    ])
  })
})

describe('placeChords', () => {
  const chord = (start: number, end: number, root: number | null): Chord => ({ start, end, root, quality: root === null ? null : 'maj', label: '' })
  const line = (start: number, words: [string, number][]) => ({
    start,
    end: words[words.length - 1][1] + 0.5,
    words: words.map(([text, s]) => ({ text, start: s, end: s + 0.5 })),
  })

  it('puts each chord over the word sung when it changes', () => {
    const lines = [line(10, [['Rey', 10], ['de', 10.6], ['Gloria', 11.2], ['digno', 13]])]
    const chords = [chord(0, 9.9, 5), chord(9.9, 12.8, 1), chord(12.8, 20, 3)]
    const [intro, row] = placeChords(lines, chords)
    expect(intro).toMatchObject({ kind: 'break', chords: [chords[0]] }) // the intro, on its own row
    expect(row.kind === 'line' && row.words.map((w) => w.chords.map((c) => c.root))).toEqual([[1], [], [], [3]])
  })

  it('carries the chord already playing onto a line, and a short pause\'s chords onto the line before', () => {
    const lines = [line(0, [['a', 0], ['b', 1]]), line(3, [['c', 3], ['d', 4]])]
    const chords = [chord(0, 2, 0), chord(2, 6, 7)]
    const rows = placeChords(lines, chords)
    const roots = rows.map((r) => (r.kind === 'line' ? r.words.map((w) => w.chords.map((c) => c.root)) : null))
    expect(roots).toEqual([[[0], [7]], [[7], []]])
  })

  it('gives a long instrumental its own row, and skips no-chord stretches', () => {
    const lines = [line(0, [['a', 0]]), line(20, [['b', 20]])]
    const chords = [chord(0, 2, 0), chord(2, 4, null), chord(8, 12, 5), chord(12, 25, 7)]
    const rows = placeChords(lines, chords)
    expect(rows.map((r) => r.kind)).toEqual(['line', 'break', 'line'])
    expect(rows[1].kind === 'break' && rows[1].chords.map((c) => c.root)).toEqual([5, 7])
    expect(lineIndexAt(lines, 19.9)).toBe(1)
    expect(lineIndexAt(lines, -1)).toBe(-1)
  })
})
