// Every chord of every key in the Keys chart, and every chord in the Chord Library, checked
// note by note: spelled right, sounding right, drawn right, and playable on a guitar.
import { describe, expect, it } from 'vitest'
import { CHORD_TYPES, ROOTS, spell, voicing } from './chords'
import { findVoicings, TUNING } from './guitar'
import { keyChart, keyInfo, parseKey, pcOf, type KeyInfo } from './keys'
import { mod12 } from './music'

const ALL_KEYS: KeyInfo[] = (['major', 'minor'] as const).flatMap((m) => [...keyChart(m).sharps, ...keyChart(m).flats])
const LETTERS = 'CDEFGAB'

describe('every key in the chart', () => {
  it('has 30 keys, each tonic once per mode', () => {
    expect(ALL_KEYS.length).toBe(30)
    expect(new Set(ALL_KEYS.map((k) => k.name)).size).toBe(30)
  })

  for (const k of ALL_KEYS) {
    it(`${k.name}`, () => {
      // The scale: seven letters, each once, in order, with the major or natural minor's steps.
      expect(k.scale.map((n) => n[0]).join('')).toBe([...LETTERS.slice(LETTERS.indexOf(k.tonic[0])), ...LETTERS].slice(0, 7).join(''))
      const steps = k.mode === 'major' ? [0, 2, 4, 5, 7, 9, 11] : [0, 2, 3, 5, 7, 8, 10]
      expect(k.scale.map((n) => mod12(pcOf(n) - k.tonicPc))).toEqual(steps)
      expect(k.scale.every((n) => !/[𝄪𝄫?]/.test(n))).toBe(true)
      // The signature: only sharps or only flats, as many as the chart says.
      const sharps = k.scale.filter((n) => n.includes('♯')).length
      const flats = k.scale.filter((n) => n.includes('♭')).length
      expect(sharps === 0 || flats === 0).toBe(true)
      expect(k.count).toBe(sharps + flats)
      // The relative key shares the signature.
      const [relTonic, relMode] = k.relative.split(' ')
      const rel = keyInfo(relTonic, relMode as 'major' | 'minor')
      expect(rel.count).toBe(k.count)
      expect(ALL_KEYS.some((x) => x.name === rel.name)).toBe(true)
      expect(rel.relative).toBe(k.name)

      for (const c of k.chords) {
        const notes = spell(c.root, c.type)
        // Every chord's notes are in the key, spelled as the key spells them.
        for (const n of notes) expect(k.scale).toContain(n)
        // They sound as the chord should.
        expect(notes.map((n) => mod12(pcOf(n) - c.rootPc))).toEqual(c.type.semitones)
        expect(c.rootPc).toBe(pcOf(c.root))
        // Its keys on a keyboard from C are the chord's, in the keyboard's two octaves.
        const keys = voicing(c.rootPc, c.type)
        expect(keys.map(mod12)).toEqual(c.type.semitones.map((s) => mod12(c.rootPc + s)))
        expect(Math.min(...keys)).toBeGreaterThanOrEqual(0)
        expect(Math.max(...keys)).toBeLessThan(24)
        // And it has a guitar shape that plays exactly its notes, with its root lowest.
        const shape = findVoicings(c.rootPc, c.type, undefined, 1)[0]
        expect(shape, `${c.symbol} in ${k.name} has no guitar shape`).toBeTruthy()
        const played = shape.frets.map((f, s) => (f >= 0 ? mod12(TUNING[s] + f) : -1)).filter((pc) => pc >= 0)
        expect(new Set(played)).toEqual(new Set(c.type.semitones.map((s) => mod12(c.rootPc + s))))
        expect(played[0]).toBe(c.rootPc)
      }
    })
  }

  it('finds the chart row for every key a song can be in', () => {
    // The engine names keys like these; each must land on a chart row with the same sound.
    for (let pc = 0; pc < 12; pc++) {
      for (const mode of ['major', 'minor'] as const) {
        for (const name of [['C', 'Db', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B'][pc], ['C', 'C#', 'D', 'D#', 'E', 'F', 'Gb', 'G', 'G#', 'A', 'A#', 'B'][pc]]) {
          const p = parseKey(`${name} ${mode}`)!
          expect(p).toEqual({ pc, mode })
          expect(ALL_KEYS.some((k) => k.tonicPc === p.pc && k.mode === p.mode)).toBe(true)
        }
      }
    }
  })
})

describe('every chord in the Chord Library', () => {
  for (const [pc, root] of ROOTS.entries()) {
    it(`${root}: all ${CHORD_TYPES.length} types`, () => {
      for (const type of CHORD_TYPES) {
        const notes = spell(root, type)
        expect(notes.every((n) => !n.includes('?')), `${root}${type.suffix}: ${notes}`).toBe(true)
        expect(new Set(notes.map((n) => n[0])).size, `${root}${type.suffix} repeats a letter`).toBe(notes.length)
        expect(notes.map((n) => mod12(pcOf(n.replace('𝄪', '♯♯').replace('𝄫', '♭♭')) - pc))).toEqual(type.semitones.map(mod12))
        const keys = voicing(pc, type)
        expect(Math.min(...keys)).toBeGreaterThanOrEqual(0)
        expect(Math.max(...keys)).toBeLessThan(36)
        const shapes = findVoicings(pc, type)
        expect(shapes.length, `${root}${type.suffix} has no guitar shape`).toBeGreaterThan(0)
        for (const s of shapes) {
          const played = s.frets.map((f, i) => (f >= 0 ? mod12(TUNING[i] + f) : -1)).filter((x) => x >= 0)
          const tones = new Set(type.semitones.map((t) => mod12(pc + t)))
          expect(played.every((x) => tones.has(x))).toBe(true)
          expect(played[0]).toBe(pc)
        }
      }
    })
  }
})
