// The key open on the Keys and Circle of Fifths pages, and the panel that shows it: its scale on
// a keyboard, its signature and relative key, its chords, and the scale or its chords played up
// and back down with each chord shown as it sounds.

import { useEffect, useRef, useState } from 'react'
import { chordSymbol, playChord, spell, voicing } from '../chords'
import { type DiatonicChord, type KeyInfo, type Mode, keyChart, keyInfo, parseKey } from '../keys'
import { openChord, useApp } from '../store'
import { Keyboard } from './Keyboard'

const STEPS = { major: [0, 2, 4, 5, 7, 9, 11], minor: [0, 2, 3, 5, 7, 8, 10] }
const ALL_KEYS = (['major', 'minor'] as const).flatMap((m) => [...keyChart(m).sharps, ...keyChart(m).flats])

// ------------------------------------------------------------------ the open key

// Shared by both pages, and kept while you look elsewhere.
let picked: { tonic: string; mode: Mode } | null = null
const listeners = new Set<() => void>()

/** The song you're playing, and whether a key is its key. */
export function useSongKey() {
  const songs = useApp((s) => s.songs)
  const songId = useApp((s) => s.songId)
  const song = songs?.find((s) => s.id === songId)
  const songKey = parseKey(song?.key)
  const isSongKey = (k: KeyInfo) => !!songKey && songKey.pc === k.tonicPc && songKey.mode === k.mode
  return { song, isSongKey }
}

/** The key open on the Keys pages: the one last picked, else the song's, else C major. */
export function usePickedKey() {
  const [, bump] = useState(0)
  const { isSongKey } = useSongKey()
  useEffect(() => {
    const l = () => bump((n) => n + 1)
    listeners.add(l)
    return () => void listeners.delete(l)
  }, [])
  const p = picked ?? (() => {
    const k = ALL_KEYS.find(isSongKey)
    return k ? { tonic: k.tonic, mode: k.mode } : { tonic: 'C', mode: 'major' as Mode }
  })()
  const choose = (k: { tonic: string; mode: Mode }) => {
    picked = { tonic: k.tonic, mode: k.mode }
    listeners.forEach((l) => l())
  }
  return { key: keyInfo(p.tonic, p.mode), choose }
}

// ------------------------------------------------------------------ the panel

export const signature = (k: KeyInfo) =>
  k.count === 0 ? 'no sharps or flats' : `${k.count} ${k.sharps ? 'sharp' : 'flat'}${k.count === 1 ? '' : 's'}`
export const playTriad = (c: DiatonicChord) => playChord(voicing(c.rootPc, c.type))

/** The scale up an octave and back down, as steps from the tonic (7 is the octave). */
const SCALE_RUN = [0, 1, 2, 3, 4, 5, 6, 7, 6, 5, 4, 3, 2, 1, 0]
const NOTE_GAP = 0.42 // seconds between the scale's notes
const CHORD_GAP = 0.8 // and between its chords

/** Where a scale step sits on the keyboard (which starts at C), and the chord built on it there. */
const stepKey = (k: KeyInfo, step: number) => (step === 7 ? k.tonicPc + 12 : k.tonicPc + STEPS[k.mode][step])
function chordKeys(k: KeyInfo, step: number) {
  const c = k.chords[step % 7]
  let keys = c.type.semitones.map((s) => stepKey(k, step) + s)
  while (Math.max(...keys) > 23) keys = keys.map((n) => n - 12)
  return keys
}

/**
 * The open key: its scale on a keyboard, its signature and relative key, and its chords. Hovering
 * a chord shows it on the keyboard; playing the scale or its chords (up and back down) shows the
 * chord on each note as it sounds.
 */
export function KeyDetail({ keyInfo: key, onChoose, className = '' }: {
  keyInfo: KeyInfo
  onChoose: (k: { tonic: string; mode: Mode }) => void
  className?: string
}) {
  const { song, isSongKey } = useSongKey()
  const lit = STEPS[key.mode].map((s) => key.tonicPc + s)

  // The chord on show: the one the scale is playing, else the one hovered.
  const [hover, setHover] = useState<number | null>(null)
  // The scale running: its notes or its chords, and how far it's got (an index into SCALE_RUN).
  const [running, setRunning] = useState<{ what: 'notes' | 'chords'; at: number } | null>(null)
  const timers = useRef<number[]>([])
  const sounds = useRef<(() => void)[]>([])
  const stop = () => {
    timers.current.forEach(clearTimeout)
    timers.current = []
    sounds.current.forEach((silence) => silence())
    sounds.current = []
    setRunning(null)
  }
  useEffect(() => stop, [])
  useEffect(stop, [key.name])
  const run = (what: 'notes' | 'chords') => {
    const again = running?.what === what
    stop()
    if (again) return // its button is Stop while it plays
    const gap = what === 'notes' ? NOTE_GAP : CHORD_GAP
    if (what === 'notes') sounds.current.push(playChord(SCALE_RUN.map((st) => stepKey(key, st)), { gap }))
    else sounds.current = SCALE_RUN.map((st, i) => playChord(chordKeys(key, st), { delay: i * gap, length: gap * 1.6 }))
    SCALE_RUN.forEach((_, i) => timers.current.push(window.setTimeout(() => setRunning({ what, at: i }), 20 + i * gap * 1000)))
    timers.current.push(window.setTimeout(() => setRunning(null), 20 + SCALE_RUN.length * gap * 1000 + 300))
  }
  const step = running !== null ? SCALE_RUN[running.at] : hover
  const shown = step !== null ? key.chords[step % 7] : null

  return (
    <section className={`panel key-detail ${className}`}>
      <div className="key-detail-head">
        <div>
          <div className="key-detail-name">{key.name}</div>
          <div className="muted">
            {signature(key)} · relative {key.mode === 'major' ? 'minor' : 'major'}:{' '}
            <button
              className="text-btn"
              onClick={() => {
                const rel = key.relative.split(' ')
                onChoose({ tonic: rel[0], mode: rel[1] as Mode })
              }}
            >
              {key.relative}
            </button>
            {isSongKey(key) && <> · the key of {song?.title ? `“${song.title}”` : 'the song you’re playing'}</>}
          </div>
        </div>
        <div className="row key-detail-play">
          {(['notes', 'chords'] as const).map((what) => (
            <button key={what} className={`pill-btn ${running?.what === what ? 'accent' : ''}`} onClick={() => run(what)}>
              {running?.what === what ? 'Stop' : what === 'notes' ? 'Play the Scale' : 'Play the Chords'}
            </button>
          ))}
        </div>
      </div>
      <div className="key-detail-keys">
        {shown && step !== null ? (
          <Keyboard lit={chordKeys(key, step)} labels={spell(shown.root, shown.type)} octaves={2} height={86} className="showing-chord" />
        ) : (
          <Keyboard lit={lit} labels={key.scale} octaves={2} height={86} />
        )}
        <div className="key-detail-caption">
          {shown ? (
            <>
              <b>{chordSymbol(shown.root, shown.type)}</b>
              <span className="muted">
                {shown.numeral} · {shown.root} {shown.type.name} · {spell(shown.root, shown.type).join(' ')}
              </span>
            </>
          ) : (
            <>
              <b>Scale</b>
              <span className="muted">{[...key.scale, key.scale[0]].join(' ')}</span>
            </>
          )}
        </div>
      </div>
      <div className="key-detail-chords">
        {key.chords.map((c, i) => (
          <div key={c.degree} className="key-detail-chord">
            <span className="muted">{c.numeral}</span>
            <button
              className={`pill-btn ${shown === c ? 'showing' : ''}`}
              title={`Play ${c.root} ${c.type.name}`}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
              onFocus={() => setHover(i)}
              onBlur={() => setHover(null)}
              onClick={() => playTriad(c)}
            >
              {chordSymbol(c.root, c.type)}
            </button>
            <button className="text-btn small" title="Open in the Chord Library" onClick={() => openChord(c.rootPc, c.type.id, c.root)}>
              Library
            </button>
          </div>
        ))}
      </div>
    </section>
  )
}
