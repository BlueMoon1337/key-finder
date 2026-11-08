import { useMemo, useState } from 'react'
import type { Chord } from '../api'
import { fromDetected, playChord, slashVoicing, spell, voicing } from '../chords'
import { chordIndexAt, chordLabel, formatTime } from '../music'
import { playback } from '../playback'
import { openChord } from '../store'
import { Keyboard } from './Keyboard'
import { useFrame } from './useFrame'

const BRIEF = 2

interface Entry {
  label: string
  chord: Chord
  first: number
  count: number
  seconds: number
}

/**
 * Every chord in the song, as a chart: each on a keyboard with its notes, in the key you're
 * playing in (Pitch) and at the detail you've chosen, in the order they first come. The chord
 * playing now is highlighted. Click one to hear it; "Go" jumps to where it's first played.
 */
export function SongChords({ chords, semitones, flatsAt }: {
  chords: Chord[]
  semitones: number
  flatsAt: (t: number) => boolean
}) {
  const entries = useMemo(() => {
    const by = new Map<string, Entry>()
    for (const c of chords) {
      if (c.root === null) continue
      const label = chordLabel(c, semitones, flatsAt(c.start))
      const e = by.get(label)
      if (e) {
        e.count++
        e.seconds += c.end - c.start
      } else by.set(label, { label, chord: c, first: c.start, count: 1, seconds: c.end - c.start })
    }
    return [...by.values()]
  }, [chords, semitones, flatsAt])
  const [now, setNow] = useState<string | null>(null)
  const [all, setAll] = useState(false)
  // Chords heard for under BRIEF seconds in all (a passing bass note, a fill) wait behind a button.
  const main = entries.filter((e) => e.seconds >= BRIEF)
  const shown = all || main.length < 4 ? entries : main

  useFrame(() => {
    const i = chordIndexAt(chords, playback.time())
    const c = chords[i]
    const label = c && c.root !== null ? chordLabel(c, semitones, flatsAt(c.start)) : null
    if (label !== now) setNow(label)
  })

  if (!entries.length) return null
  return (
    <section className="panel song-chords">
      <h2>
        Chords <span className="muted">{entries.length} in this song · click one to hear it</span>
      </h2>
      <div className="chord-grid">
        {shown.map((e) => {
          const c = fromDetected(e.chord, semitones, flatsAt(e.first))
          if (!c) return null
          const notes = spell(c.root, c.type)
          const v = c.bassPc !== undefined ? slashVoicing(c.rootPc, c.type, c.bassPc) : null
          const lit = v ? v.chord : voicing(c.rootPc, c.type)
          const octaves = v ? v.octaves : Math.ceil((Math.max(...lit) + 1) / 12)
          return (
            <div key={e.label} className={`chord-card ${e.label === now ? 'now' : ''}`}>
              <button className="chord-card-main" title={`Play ${e.label}`} onClick={() => playChord(lit, { bass: v?.bass })}>
                <span className="chord-card-name">{e.label}</span>
                <Keyboard lit={lit} bass={v?.bass} octaves={Math.max(2, octaves)} height={46} />
                <span className="chord-card-notes">
                  {notes.join(' ')}
                  {c.bass ? ` / ${c.bass}` : ''}
                </span>
              </button>
              <span className="chord-card-meta" title={`Played ${e.count} times, ${formatTime(e.seconds)} in all`}>
                {e.count}× · {formatTime(e.seconds)}
              </span>
              <span className="chord-card-actions">
                <button className="text-btn small" onClick={() => playback.seek(e.first)} title="Go to where it's first played">
                  ▸ {formatTime(e.first)}
                </button>
                <button className="text-btn small" onClick={() => openChord(c.rootPc, c.type.id)} title="Open in the Chord Library">
                  Library
                </button>
              </span>
            </div>
          )
        })}
      </div>
      {entries.length > shown.length && (
        <button className="text-btn small chord-more" onClick={() => setAll(true)}>
          Show {entries.length - shown.length} brief chords (under {BRIEF} seconds in all)
        </button>
      )}
      {all && main.length >= 4 && main.length < entries.length && (
        <button className="text-btn small chord-more" onClick={() => setAll(false)}>
          Hide the brief chords
        </button>
      )}
    </section>
  )
}
