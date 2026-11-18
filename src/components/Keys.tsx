import { useEffect, useState } from 'react'
import { spell, voicing } from '../chords'
import { findVoicings } from '../guitar'
import { type DiatonicChord, DEGREE_HEADINGS, type KeyInfo, type Mode, keyChart } from '../keys'
import { useApp } from '../store'
import { ChordDiagram } from './ChordDiagram'
import { KeyDetail, playTriad, signature, usePickedKey, useSongKey } from './KeyDetail'
import { Keyboard } from './Keyboard'

const CHARTS = { major: keyChart('major'), minor: keyChart('minor') }

/** A chord from the chart, shown beside the cell it's hovered in: on a keyboard, and on a guitar if that's the chord view. */
function ChordPeek({ peek }: { peek: { chord: DiatonicChord; key: KeyInfo; rect: DOMRect } }) {
  const view = useApp((s) => s.settings.chordView)
  const { chord, key, rect } = peek
  const notes = spell(chord.root, chord.type)
  const shape = view === 'guitar' ? findVoicings(chord.rootPc, chord.type, undefined, 1)[0] : undefined
  const height = shape ? 250 : 140
  const above = rect.top > height + 16
  const left = Math.max(8, Math.min(rect.left, window.innerWidth - 236))
  return (
    <div className="chord-peek" style={above ? { left, top: rect.top - 8, transform: 'translateY(-100%)' } : { left, top: rect.bottom + 8 }} role="tooltip">
      <div className="chord-peek-head">
        <b>{chord.symbol}</b>
        <span className="muted">
          {chord.numeral} in {key.name}
        </span>
      </div>
      <Keyboard lit={voicing(chord.rootPc, chord.type)} labels={notes} octaves={2} height={52} />
      {shape && <ChordDiagram voicing={shape} rootPc={chord.rootPc} height={104} />}
      <span className="muted">{notes.join(' ')}</span>
    </div>
  )
}

/**
 * The major and minor keys as a chart: for each key, the chord on each note of its scale and
 * its key signature, sharp keys and flat keys apart. Click a chord to hear it; the key it's in
 * opens above. Hovering a chord shows its notes. The playing song's key is marked.
 */
export function Keys() {
  const { song, isSongKey } = useSongKey()
  const { key, choose } = usePickedKey()

  // A chord hovered in the chart, shown beside it.
  const [peek, setPeek] = useState<{ chord: DiatonicChord; key: KeyInfo; rect: DOMRect } | null>(null)
  useEffect(() => {
    if (!peek) return
    const hide = () => setPeek(null)
    window.addEventListener('scroll', hide, true)
    return () => window.removeEventListener('scroll', hide, true)
  }, [peek])

  const table = (mode: Mode, keys: KeyInfo[], sharps: boolean) => (
    <div className="keys-table-wrap">
      <table className="keys-table">
        <thead>
          <tr>
            {DEGREE_HEADINGS[mode].map((h) => (
              <th key={h} scope="col">
                {h}
              </th>
            ))}
            <th scope="col">{sharps ? 'Sharps' : 'Flats'}</th>
          </tr>
        </thead>
        <tbody>
          {keys.map((k) => {
            const picked = k.tonic === key.tonic && k.mode === key.mode
            return (
              <tr key={k.tonic} className={`${picked ? 'picked' : ''} ${isSongKey(k) ? 'song-key' : ''}`}>
                {k.chords.map((c) => (
                  <td key={c.degree}>
                    <button
                      className="keys-chord"
                      aria-label={`${c.numeral} in ${k.name}: ${c.root} ${c.type.name}`}
                      onMouseEnter={(ev) => setPeek({ chord: c, key: k, rect: ev.currentTarget.getBoundingClientRect() })}
                      onMouseLeave={() => setPeek(null)}
                      onFocus={(ev) => setPeek({ chord: c, key: k, rect: ev.currentTarget.getBoundingClientRect() })}
                      onBlur={() => setPeek(null)}
                      onClick={() => {
                        choose(k)
                        playTriad(c)
                      }}
                    >
                      {c.symbol}
                    </button>
                  </td>
                ))}
                <td className="keys-count">
                  <button className="keys-chord" title={`${k.name}: ${signature(k)}`} onClick={() => choose(k)}>
                    {k.count}
                    {sharps ? '♯' : '♭'}
                  </button>
                  {isSongKey(k) && (
                    <span className="keys-song" title={`${song?.title || 'The song you’re playing'} is in ${k.name}`}>
                      ♪
                    </span>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )

  return (
    <main className="page keys-page">
      <h1>Keys</h1>
      <KeyDetail keyInfo={key} onChoose={choose} />
      {(['major', 'minor'] as const).map((mode) => (
        <section key={mode} className="panel keys-chart">
          <h2>{mode === 'major' ? 'Major Keys and Scales' : 'Minor Keys and Scales'}</h2>
          {table(mode, CHARTS[mode].sharps, true)}
          {table(mode, CHARTS[mode].flats, false)}
        </section>
      ))}
      {peek && <ChordPeek peek={peek} />}
    </main>
  )
}
