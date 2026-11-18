import { describe, expect, it } from 'vitest'
import { CIRCLE } from './components/CircleOfFifths'
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
})
