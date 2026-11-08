import { useMemo } from 'react'
import type { SongSummary } from '../api'
import { CHORD_GROUPS, CHORD_TYPES, ROOTS, chordSymbol, inversionCount, playChord, spell, typeById, voicing } from '../chords'
import { navigate, openChord, useApp } from '../store'
import { Keyboard } from './Keyboard'

const INTERVAL_NAMES: Record<string, string> = {
  '1': 'root',
  '2': 'major second',
  '♭3': 'minor third',
  '3': 'major third',
  '4': 'perfect fourth',
  '♭5': 'diminished fifth',
  '5': 'perfect fifth',
  '♯5': 'augmented fifth',
  '6': 'major sixth',
  '𝄫7': 'diminished seventh',
  '♭7': 'minor seventh',
  '7': 'major seventh',
  '9': 'major ninth',
}
const INVERSION_NAMES = ['Root position', 'First inversion', 'Second inversion', 'Third inversion']

/**
 * Every chord, as a reference: pick a root and a type to see it on a keyboard with its notes,
 * intervals and inversions, and hear it. The chords your songs use are marked, and each one
 * lists the songs it's in.
 */
export function ChordLibrary() {
  const pick = useApp((s) => s.chord)
  const songs = useApp((s) => s.songs)
  const type = typeById(pick.type) ?? CHORD_TYPES[0]
  const root = ROOTS[pick.root]
  const notes = spell(root, type)
  const keys = voicing(pick.root, type)
  const octaves = Math.ceil((Math.max(...keys) + 1) / 12)

  // Which songs use each chord ("7:maj"), from the library.
  const usage = useMemo(() => {
    const by = new Map<string, SongSummary[]>()
    for (const s of songs ?? []) for (const c of s.chords ?? []) by.set(c, [...(by.get(c) ?? []), s])
    return by
  }, [songs])
  const inSongs = usage.get(`${pick.root}:${type.id}`) ?? []
  const used = [...usage.entries()]
    .map(([k, list]) => {
      const [r, q] = k.split(':')
      return { root: Number(r), type: typeById(q), count: list.length }
    })
    .filter((u) => u.type)
    .sort((a, b) => b.count - a.count || a.root - b.root)

  return (
    <main className="page chord-library">
      <h1>Chords</h1>

      <section className="panel">
        <div className="chord-roots" role="radiogroup" aria-label="Root">
          {ROOTS.map((r, i) => (
            <button key={r} role="radio" aria-checked={i === pick.root} className={i === pick.root ? 'active' : ''} onClick={() => openChord(i, type.id)}>
              {r}
            </button>
          ))}
        </div>
        {CHORD_GROUPS.map((g) => (
          <div className="chord-group" key={g}>
            <span className="label">{g}</span>
            <div className="chord-types">
              {CHORD_TYPES.filter((t) => t.group === g).map((t) => (
                <button key={t.id} className={`chip ${t.id === type.id ? 'active' : ''}`} title={`${root} ${t.name}`} onClick={() => openChord(pick.root, t.id)}>
                  {chordSymbol(root, t)}
                  {usage.has(`${pick.root}:${t.id}`) && <i className="used-dot" aria-label="In your songs" />}
                </button>
              ))}
            </div>
          </div>
        ))}
      </section>

      <section className="panel chord-detail">
        <div className="chord-title">
          <div>
            <h2 className="chord-symbol">{chordSymbol(root, type)}</h2>
            <span className="muted">
              {root} {type.name}
            </span>
          </div>
          <div className="row">
            <button className="pill-btn accent" onClick={() => playChord(keys)}>
              ▶ Play
            </button>
            <button className="pill-btn" onClick={() => playChord(keys, { arpeggio: true })}>
              Arpeggio
            </button>
          </div>
        </div>
        <Keyboard lit={keys} labels={notes} octaves={Math.max(2, octaves)} height={150} className="big" />
        <dl className="chord-facts">
          <div>
            <dt>Notes</dt>
            <dd>{notes.join('  ')}</dd>
          </div>
          <div>
            <dt>Formula</dt>
            <dd>{type.degrees.join('  ')}</dd>
          </div>
          <div>
            <dt>Intervals</dt>
            <dd>{type.degrees.map((d) => INTERVAL_NAMES[d] ?? d).join(', ')}</dd>
          </div>
        </dl>

        <h3>Inversions</h3>
        <div className="inversions">
          {Array.from({ length: inversionCount(type) + 1 }, (_, i) => {
            const v = voicing(pick.root, type, i)
            const order = [...notes.slice(i), ...notes.slice(0, i)]
            return (
              <button key={i} className="inversion" onClick={() => playChord(v)} title="Play">
                <span className="label">{INVERSION_NAMES[i]}</span>
                <Keyboard lit={v} labels={order} octaves={Math.max(2, Math.ceil((Math.max(...v) + 1) / 12))} height={64} />
                <span className="muted">
                  {i === 0 ? chordSymbol(root, type) : chordSymbol(root, type, notes[i])} · {order.join(' ')}
                </span>
              </button>
            )
          })}
        </div>

        <h3>In your songs</h3>
        {inSongs.length ? (
          <ul className="chord-songs">
            {inSongs.map((s) => (
              <li key={s.id}>
                <button className="text-btn" onClick={() => navigate('player', s.id)}>
                  {s.title}
                </button>
                <span className="muted">
                  {s.artist ? ` · ${s.artist}` : ''}
                  {s.key ? ` · ${s.key}` : ''}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="hint">None of your songs use {chordSymbol(root, type)}.</p>
        )}
      </section>

      {used.length > 0 && (
        <section className="panel">
          <h2>Chords in your library</h2>
          <p className="hint">Every chord KeyFinder has found in your songs, the most used first. Pick one to see it.</p>
          <div className="chord-types">
            {used.map((u) => (
              <button key={`${u.root}:${u.type!.id}`} className="chip" onClick={() => openChord(u.root, u.type!.id)}>
                {chordSymbol(ROOTS[u.root], u.type!)} <span className="muted">{u.count}</span>
              </button>
            ))}
          </div>
        </section>
      )}
    </main>
  )
}
