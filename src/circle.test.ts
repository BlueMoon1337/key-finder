import { describe, expect, it } from 'vitest'
import { CIRCLE, accidentals, relativeMinor } from './components/CircleOfFifths'
import { keyInfo, pcOf } from './keys'
import { mod12 } from './music'

describe('circle of fifths', () => {
  it('goes up a fifth each step clockwise, from C round to C', () => {
    expect(CIRCLE.length).toBe(12)
    CIRCLE.forEach((spot, i) => {
      for (const k of spot.keys) expect(pcOf(k.tonic)).toBe(mod12(7 * i))
    })
  })

  it("gives every key its own signature, as the keys chart has it", () => {
    const all = CIRCLE.flatMap((s) => s.keys)
    expect(all.length).toBe(15) // C, 7 sharp keys, 7 flat keys
    for (const k of all) {
      const info = keyInfo(k.tonic, 'major')
      expect(info.count).toBe(k.sharps + k.flats)
      expect(info.sharps).toBe(k.flats === 0)
    }
    // A sharp more each step clockwise from C, a flat more each step anticlockwise.
    expect(CIRCLE.slice(0, 8).map((s) => s.keys.find((k) => !k.flats)!.sharps)).toEqual([0, 1, 2, 3, 4, 5, 6, 7])
    expect([0, 11, 10, 9, 8, 7, 6, 5].map((i) => CIRCLE[i].keys.find((k) => !k.sharps)!.flats)).toEqual([0, 1, 2, 3, 4, 5, 6, 7])
  })
  it('rings each major key with its relative minor', () => {
    expect(CIRCLE.map((s) => s.keys.map((k) => relativeMinor(k.tonic)).join('/'))).toEqual([
      'A', 'E', 'B', 'F♯', 'C♯', 'G♯/A♭', 'E♭/D♯', 'B♭/A♯', 'F', 'C', 'G', 'D',
    ])
  })

  it('names the sharps or flats a key has, in signature order', () => {
    expect(accidentals({ tonic: 'C', mode: 'major' })).toEqual([])
    expect(accidentals({ tonic: 'D', mode: 'major' })).toEqual(['F♯', 'C♯'])
    expect(accidentals({ tonic: 'B', mode: 'minor' })).toEqual(['F♯', 'C♯'])
    expect(accidentals({ tonic: 'C♯', mode: 'major' })).toEqual(['F♯', 'C♯', 'G♯', 'D♯', 'A♯', 'E♯', 'B♯'])
    expect(accidentals({ tonic: 'A♭', mode: 'major' })).toEqual(['B♭', 'E♭', 'A♭', 'D♭'])
    expect(accidentals({ tonic: 'A♭', mode: 'minor' })).toEqual(['B♭', 'E♭', 'A♭', 'D♭', 'G♭', 'C♭', 'F♭'])
    // And they're the notes the key's scale actually alters.
    for (const s of CIRCLE) {
      for (const k of s.keys) {
        for (const mode of ['major', 'minor'] as const) {
          const tonic = mode === 'major' ? k.tonic : relativeMinor(k.tonic)
          const altered = keyInfo(tonic, mode).scale.filter((n) => n.length > 1)
          expect([...accidentals({ tonic, mode })].sort()).toEqual([...altered].sort())
        }
      }
    }
  })
})
