// Guitar chord shapes, worked out rather than looked up: every way to play a chord in standard
// tuning within a four-fret hand span, kept when a hand can play it, best first. Open chords come
// out as the shapes everyone learns (C = x32010, Am = x02210), then barre shapes up the neck.

import type { ChordType } from './chords'
import { mod12 } from './music'

/** Standard tuning, low E to high E, as MIDI notes. */
export const TUNING = [40, 45, 50, 55, 59, 64]
export const STRING_NAMES = ['E', 'A', 'D', 'G', 'B', 'E']

/** A fingering: the fret of each string, low E first; -1 is not played, 0 is open. */
export type Frets = number[]

export interface Voicing {
  frets: Frets
  /** The lowest fretted fret (1 for open chords), where the diagram starts. */
  base: number
  /** A finger laid across several strings at one fret, if the shape needs it. */
  barre: { fret: number; from: number; to: number } | null
  /** Which finger presses each string (1 index … 4 little), 0 for open or not played. */
  fingers: number[]
  /** The notes it sounds, low to high, as MIDI numbers. */
  midi: number[]
}

const SPAN = 4 // frets a hand covers
const MAX_FRET = 15

/**
 * The fingers a fingering needs, and the barre it uses if it needs one. Fingers go to frets from
 * the nut up, one per string, except that the lowest fret can be a barre: the index finger across
 * every string from the lowest one at that fret up to the top, where none of those strings is open.
 */
function fingering(frets: Frets): { count: number; barre: Voicing['barre']; fingers: number[] } | null {
  const pressed = frets.map((f, s) => [f, s] as const).filter(([f]) => f > 0)
  const fingers = frets.map(() => 0)
  if (pressed.length === 0) return { count: 0, barre: null, fingers }
  const low = Math.min(...pressed.map(([f]) => f))
  const atLow = pressed.filter(([f]) => f === low).map(([, s]) => s)
  // Plain fingering: one finger per pressed string, in fret order then string order.
  const order = [...pressed].sort((a, b) => a[0] - b[0] || a[1] - b[1])
  if (order.length <= 4) {
    order.forEach(([, s], i) => (fingers[s] = i + 1))
    return { count: order.length, barre: null, fingers }
  }
  // A barre at the lowest fret, from its lowest string up: every string above must be played, not open.
  if (atLow.length >= 2) {
    const from = atLow[0]
    const to = 5
    for (let s = from; s <= to; s++) if (frets[s] <= 0) return null
    const rest = order.filter(([f]) => f > low)
    if (rest.length > 3) return null
    for (let s = from; s <= to; s++) if (frets[s] === low) fingers[s] = 1
    rest.forEach(([, s], i) => (fingers[s] = i + 2))
    return { count: 1 + rest.length, barre: { fret: low, from, to }, fingers }
  }
  return null
}

/**
 * Playable fingerings of a chord, best first: the notes are the chord's (the fifth may be left
 * out of a chord of four notes or more), every note of the chord that must sound does, the lowest
 * note is the root (or ``bass``, for a slash chord), only the lowest strings go unplayed, and a
 * hand can reach and finger it.
 */
export function findVoicings(rootPc: number, type: ChordType, bassPc?: number, limit = 4): Voicing[] {
  const tones = new Set(type.semitones.map((s) => mod12(rootPc + s)))
  const fifth = mod12(rootPc + 7)
  const required = new Set([...tones].filter((pc) => !(type.semitones.length >= 4 && pc === fifth && type.semitones.includes(7))))
  const bass = bassPc ?? rootPc
  if (bassPc !== undefined) tones.add(mod12(bassPc))
  const found: { v: Voicing; score: number }[] = []
  const seen = new Set<string>()

  for (let start = 0; start <= MAX_FRET - SPAN + 1; start++) {
    // Each string: unplayed, open, or a fret in this hand position.
    const options = [-1, 0, ...Array.from({ length: SPAN }, (_, i) => start + i).filter((f) => f > 0)]
    const frets: Frets = [0, 0, 0, 0, 0, 0]
    const walk = (s: number) => {
      if (s === 6) return consider(frets.slice())
      for (const f of options) {
        if (f >= 0 && !tones.has(mod12(TUNING[s] + f))) continue
        frets[s] = f
        walk(s + 1)
      }
    }
    const consider = (fr: Frets) => {
      const first = fr.findIndex((f) => f >= 0)
      if (first < 0 || first > 2) return // at least four strings sound
      if (fr.slice(first).some((f) => f < 0)) return // no unplayed string among the played ones
      if (mod12(TUNING[first] + fr[first]) !== mod12(bass)) return
      const played = fr.map((f, s) => (f >= 0 ? mod12(TUNING[s] + f) : -1)).filter((pc) => pc >= 0)
      for (const pc of required) if (!played.includes(pc)) return
      if (bassPc !== undefined && !played.includes(mod12(rootPc))) return
      const pressed = fr.filter((f) => f > 0)
      if (pressed.length && Math.max(...pressed) - Math.min(...pressed) >= SPAN) return
      const fing = fingering(fr)
      if (!fing) return
      const key = fr.join(',')
      if (seen.has(key)) return
      seen.add(key)
      const low = pressed.length ? Math.min(...pressed) : 0
      const opens = fr.filter((f) => f === 0).length
      const muted = first
      // Lower on the neck, fewer fingers and unplayed strings, open strings near the nut, a
      // narrow stretch, and the root doubled are what make a shape comfortable and full.
      const roots = played.filter((pc) => pc === mod12(rootPc)).length
      const stretch = pressed.length ? Math.max(...pressed) - low : 0
      // Open strings belong to first-position shapes; mixed into a shape higher up they're awkward,
      // and so is one wedged between fretted strings when either of those is at the 3rd fret or up
      // (C's open G, between frets 2 and 1, is easy; x10331's open D, between 1 and 3, isn't).
      const high = pressed.length ? Math.max(...pressed) : 0
      let wedged = 0
      for (let s = first + 1; s < 5; s++) {
        if (fr[s] !== 0) continue
        const below = fr.slice(first, s).filter((f) => f > 0).pop()
        const above = fr.slice(s + 1).find((f) => f > 0)
        if (below !== undefined && above !== undefined && Math.max(below, above) >= 3) wedged++
      }
      const openScore = (high <= 3 ? -opens * 0.5 : opens * 0.6) + wedged * 1.5
      // Two fingers on one fret, strings apart, with an open string ringing between them (no
      // barre can cover it) or a barred string under them, make the hand cross over itself:
      // x31013 for Cm, x31313 for Cm7, where x35543 and x35343 are what's played.
      let crossed = 0
      for (let a = first; a < 6; a++) {
        for (let b = a + 2; b < 6; b++) {
          const f = fr[a]
          if (f <= 0 || fr[b] !== f || (fing.barre && f === fing.barre.fret)) continue
          if (a === 0 && b === 5) continue // the two E strings (open G's 3rd frets): fingers at the edges, not crossing
          const between = fr.slice(a + 1, b)
          if (between.some((g) => g === 0) || (fing.barre && between.some((g) => g === fing.barre!.fret))) crossed++
        }
      }
      const score =
        low * 1.2 + fing.count * 0.6 + muted * 1.1 + stretch * 0.5 + openScore - Math.min(roots, 2) * 0.4 + (fing.barre ? 0.8 : 0) +
        crossed * 2
      found.push({
        v: {
          frets: fr,
          base: Math.max(1, low),
          barre: fing.barre,
          fingers: fing.fingers,
          midi: fr.map((f, s) => (f >= 0 ? TUNING[s] + f : -1)).filter((m) => m >= 0),
        },
        score,
      })
    }
    walk(0)
  }
  found.sort((a, b) => a.score - b.score)
  // The best, then the best each further up the neck, so the choices are different shapes.
  const out: Voicing[] = []
  for (const { v } of found) {
    if (out.length >= limit) break
    if (out.every((o) => Math.abs(o.base - v.base) >= 3 || (o.base <= 3 && v.base <= 3 && out.length === 0))) out.push(v)
  }
  return out
}

/** A fingering written the usual way, low E first: "x32010", with frets over 9 in brackets. */
export function fretString(frets: Frets) {
  return frets.map((f) => (f < 0 ? 'x' : f > 9 ? `(${f})` : String(f))).join('')
}
