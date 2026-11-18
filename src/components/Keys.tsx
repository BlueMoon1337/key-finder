import { useState } from 'react'
import { chordSymbol, playChord, voicing } from '../chords'
import { type DiatonicChord, DEGREE_HEADINGS, type KeyInfo, type Mode, keyChart, keyInfo, parseKey } from '../keys'
import { openChord, useApp } from '../store'
import { Keyboard } from './Keyboard'

const CHARTS = { major: keyChart('major'), minor: keyChart('minor') }
const STEPS = { major: [0, 2, 4, 5, 7, 9, 11], minor: [0, 2, 3, 5, 7, 8, 10] }

// The key picked stays picked while you look elsewhere.
let remembered: { tonic: string; mode: Mode } | null = null

const signature = (k: KeyInfo) => (k.count === 0 ? 'no sharps or flats' : `${k.count} ${k.sharps ? 'sharp' : 'flat'}${k.count === 1 ? '' : 's'}`)
const playTriad = (c: DiatonicChord) => playChord(voicing(c.rootPc, c.type))

/**
 * The major and minor keys as a chart: for each key, the chord on each note of its scale and
 * its key signature, sharp keys and flat keys apart. Click a chord to hear it; the key it's in
 * opens above, with its scale on a keyboard. The key of the song you're playing is marked.
 */
export function Keys() {
  const songs = useApp((s) => s.songs)
  const songId = useApp((s) => s.songId)
  const song = songs?.find((s) => s.id === songId)
  const songKey = parseKey(song?.key)
  const isSongKey = (k: KeyInfo) => !!songKey && songKey.pc === k.tonicPc && songKey.mode === k.mode

  const [pick, setPick] = useState(() => {
    if (remembered) return remembered
    const all = [...CHARTS.major.sharps, ...CHARTS.major.flats, ...CHARTS.minor.sharps, ...CHARTS.minor.flats]
    const k = all.find(isSongKey)
    return k ? { tonic: k.tonic, mode: k.mode } : { tonic: 'C', mode: 'major' as Mode }
  })
  const choose = (k: KeyInfo) => {
    remembered = { tonic: k.tonic, mode: k.mode }
    setPick(remembered)
  }
  const key = keyInfo(pick.tonic, pick.mode)
  const lit = STEPS[key.mode].map((s) => key.tonicPc + s)
  const playScale = () => playChord([...lit, key.tonicPc + 12], { arpeggio: true })

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
                      title={`${c.numeral} in ${k.name}: ${c.root} ${c.type.name}. Click to hear it.`}
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
      <section className="panel key-detail">
        <div className="key-detail-head">
          <div>
            <div className="key-detail-name">{key.name}</div>
            <div className="muted">
              {signature(key)} · relative {key.mode === 'major' ? 'minor' : 'major'}:{' '}
              <button
                className="text-btn"
                onClick={() => {
                  const rel = key.relative.split(' ')
                  choose(keyInfo(rel[0], rel[1] as Mode))
                }}
              >
                {key.relative}
              </button>
              {isSongKey(key) && <> · the key of {song?.title ? `“${song.title}”` : 'the song you’re playing'}</>}
            </div>
          </div>
          <button className="pill-btn" onClick={playScale}>
            Play the Scale
          </button>
        </div>
        <Keyboard lit={lit} labels={key.scale} octaves={2} height={86} />
        <div className="key-detail-chords">
          {key.chords.map((c) => (
            <div key={c.degree} className="key-detail-chord">
              <span className="muted">{c.numeral}</span>
              <button className="pill-btn" title={`Play ${c.root} ${c.type.name}`} onClick={() => playTriad(c)}>
                {chordSymbol(c.root, c.type)}
              </button>
              <button className="text-btn small" title="Open in the Chord Library" onClick={() => openChord(c.rootPc, c.type.id)}>
                Library
              </button>
            </div>
          ))}
        </div>
      </section>

      {(['major', 'minor'] as const).map((mode) => (
        <section key={mode} className="panel keys-chart">
          <h2>{mode === 'major' ? 'Major Keys and Scales' : 'Minor Keys and Scales'}</h2>
          {table(mode, CHARTS[mode].sharps, true)}
          {table(mode, CHARTS[mode].flats, false)}
        </section>
      ))}
    </main>
  )
}
