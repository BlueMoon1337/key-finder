import { describe, expect, it } from 'vitest'
import { typeById } from './chords'
import { findVoicings, fretString } from './guitar'

const PC: Record<string, number> = { C: 0, 'C#': 1, Db: 1, D: 2, Eb: 3, E: 4, F: 5, 'F#': 6, G: 7, Ab: 8, A: 9, Bb: 10, B: 11 }
const best = (root: string, type: string, bass?: string) =>
  findVoicings(PC[root], typeById(type)!, bass ? PC[bass] : undefined).map((v) => fretString(v.frets))

describe('guitar voicings', () => {
  it.each([
    ['C', 'maj', ['x32010']],
    ['G', 'maj', ['320003', '320033']],
    ['D', 'maj', ['xx0232']],
    ['A', 'maj', ['x02220']],
    ['E', 'maj', ['022100']],
    ['F', 'maj', ['133211', 'xx3211']],
    ['A', 'min', ['x02210']],
    ['E', 'min', ['022000']],
    ['D', 'min', ['xx0231']],
    ['B', 'min', ['x24432']],
    ['Bb', 'maj', ['x13331']],
    ['F#', 'min', ['244222']],
    ['E', '7', ['020100']],
    ['A', '7', ['x02020']],
    ['D', '7', ['xx0212']],
    ['G', '7', ['320001']],
    ['C', '7', ['x32310']],
    ['B', '7', ['x21202']],
    ['C', 'maj7', ['x32000']],
    ['A', 'min7', ['x02010']],
    ['E', 'min7', ['022030', '020000']],
    ['D', 'sus4', ['xx0233']],
    ['C', 'min', ['x35543']],
    ['C', 'min7', ['x35343']],
    ['Bb', '7', ['x13131']],
    ['F', 'min', ['133111']],
    ['Eb', 'maj', ['xx1343', 'x65343']],
    ['A', 'sus2', ['x02200']],
  ])('%s%s opens with a shape players know', (root, type, shapes) => {
    expect(shapes).toContain(best(root, type)[0])
  })

  it('offers other shapes further up the neck', () => {
    const v = findVoicings(PC.A, typeById('maj')!)
    expect(v.length).toBeGreaterThanOrEqual(3)
    expect(new Set(v.map((x) => x.base)).size).toBe(v.length)
    expect(v.some((x) => fretString(x.frets) === '577655')).toBe(true) // the E-shape barre at the 5th fret
  })

  it('puts a slash chord\'s bass lowest, and fingers barres with the index finger', () => {
    expect(best('G', 'maj', 'B')[0]).toMatch(/^x2/) // G/B: B on the A string
    const f = findVoicings(PC.F, typeById('maj')!).find((x) => fretString(x.frets) === '133211')!
    expect(f.barre).toEqual({ fret: 1, from: 0, to: 5 })
    expect(f.fingers).toEqual([1, 3, 4, 2, 1, 1])
  })
})
