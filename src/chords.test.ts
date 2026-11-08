import { describe, expect, it } from 'vitest'
import { chordLabel } from './music'
import { CHORD_TYPES, fromDetected, slashVoicing, spell, typeById, voicing } from './chords'

const type = (id: string) => typeById(id)!

describe('spell', () => {
  it('spells each note by its degree, as a musician would', () => {
    expect(spell('E♭', type('min7'))).toEqual(['E♭', 'G♭', 'B♭', 'D♭'])
    expect(spell('B', type('maj7'))).toEqual(['B', 'D♯', 'F♯', 'A♯'])
    expect(spell('F♯', type('7'))).toEqual(['F♯', 'A♯', 'C♯', 'E'])
    expect(spell('C', type('dim7'))).toEqual(['C', 'E♭', 'G♭', 'B𝄫'])
    expect(spell('G', type('aug'))).toEqual(['G', 'B', 'D♯'])
    expect(spell('A', type('9'))).toEqual(['A', 'C♯', 'E', 'G', 'B'])
    expect(spell('D♭', type('sus4'))).toEqual(['D♭', 'G♭', 'A♭'])
    expect(spell('Bb', type('m7b5'))).toEqual(['B♭', 'D♭', 'F♭', 'A♭'])
  })

  it('has a formula for every type that matches its semitones', () => {
    for (const t of CHORD_TYPES) {
      expect(t.semitones.length).toBe(t.degrees.length)
      expect(t.semitones[0]).toBe(0)
      expect([...t.semitones].sort((a, b) => a - b)).toEqual(t.semitones)
    }
    expect(type('9').semitones).toEqual([0, 4, 7, 10, 14])
  })
})

describe('voicings', () => {
  it('lights root position and inversions from the first octave', () => {
    expect(voicing(7, type('maj'))).toEqual([7, 11, 14]) // G B D
    expect(voicing(7, type('maj'), 1)).toEqual([11, 14, 19]) // B D G
    expect(voicing(7, type('maj'), 2)).toEqual([2, 7, 11]) // D G B, brought down an octave
  })

  it('puts a slash chord\'s bass under the chord', () => {
    expect(slashVoicing(7, type('maj'), 11)).toEqual({ bass: 11, chord: [19, 23, 26], octaves: 3 }) // G/B
    expect(slashVoicing(0, type('maj'), 4)).toEqual({ bass: 4, chord: [12, 16, 19], octaves: 2 }) // C/E
  })
})

describe('fromDetected', () => {
  it('names a detected chord in the key it\'s played in', () => {
    const c = fromDetected({ root: 7, quality: 'maj', bass: 11 }, 2, false)!
    expect([c.root, c.type.id, c.bass, c.rootPc, c.bassPc]).toEqual(['A', 'maj', 'C♯', 9, 1])
    expect(fromDetected({ root: 3, quality: 'min7', bass: null }, 0, true)!.root).toBe('E♭')
    expect(fromDetected({ root: null, quality: null, bass: null }, 0, true)).toBeNull()
    // Spelled as written, not as a double flat: F♯m in a flat key, B♭ in a sharp one.
    expect(fromDetected({ root: 6, quality: 'min', bass: null }, 0, true)!.root).toBe('F♯')
    expect(fromDetected({ root: 10, quality: 'maj', bass: null }, 0, false)!.root).toBe('B♭')
  })
})

describe('chordLabel spelling', () => {
  it('names awkward roots the way charts do', () => {
    expect(chordLabel({ root: 6, quality: 'min', bass: null }, 0, true)).toBe('F#m')
    expect(chordLabel({ root: 6, quality: 'maj', bass: null }, 0, true)).toBe('Gb')
    expect(chordLabel({ root: 3, quality: 'maj', bass: null }, 0, false)).toBe('Eb')
    expect(chordLabel({ root: 1, quality: 'min7', bass: 4 }, 0, true)).toBe('C#m7/E')
  })
})
