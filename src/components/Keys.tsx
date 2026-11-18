import { useEffect, useRef, useState } from 'react'
import { chordSymbol, playChord, spell, voicing } from '../chords'
import { findVoicings } from '../guitar'
import { type DiatonicChord, DEGREE_HEADINGS, type KeyInfo, type Mode, keyChart, keyInfo, parseKey } from '../keys'
import { openChord, useApp } from '../store'
import { ChordDiagram } from './ChordDiagram'
import { Keyboard } from './Keyboard'

const CHARTS = { major: keyChart('major'), minor: keyChart('minor') }
const STEPS = { major: [0, 2, 4, 5, 7, 9, 11], minor: [0, 2, 3, 5, 7, 8, 10] }

// The key picked stays picked while you look elsewhere.
let remembered: { tonic: string; mode: Mode } | null = null

const signature = (k: KeyInfo) => (k.count === 0 ? 'no sharps or flats' : `${k.count} ${k.sharps ? 'sharp' : 'flat'}${k.count === 1 ? '' : 's'}`)
const playTriad = (c: DiatonicChord) => playChord(voicing(c.rootPc, c.type))

/** The scale up an octave and back down, as steps from the tonic (7 is the octave). */
const SCALE_RUN = [0, 1, 2, 3, 4, 5, 6, 7, 6, 5, 4, 3, 2, 1, 0]
const NOTE_GAP = 0.42 // seconds between the scale's notes

/** Where a scale step sits on the keyboard (which starts at C), and the chord built on it there. */
const stepKey = (k: KeyInfo, step: number) => (step === 7 ? k.tonicPc + 12 : k.tonicPc + STEPS[k.mode][step])
function chordKeys(k: KeyInfo, step: number) {
  const c = k.chords[step % 7]
  let keys = c.type.semitones.map((s) => stepKey(k, step) + s)
  while (Math.max(...keys) > 23) keys = keys.map((n) => n - 12)
  return keys
}

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
 * opens above, with its scale on a keyboard. Hovering a chord shows its notes; playing the scale
 * (up and back down) shows the chord on each note as it sounds. The playing song's key is marked.
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

  // The chord on show above the chart: the one the scale is playing, else the one hovered.
  const [hover, setHover] = useState<number | null>(null)
  const [running, setRunning] = useState<number | null>(null) // index into SCALE_RUN
  const timers = useRef<number[]>([])
  const stop = () => {
    timers.current.forEach(clearTimeout)
    timers.current = []
    setRunning(null)
  }
  useEffect(() => stop, [])
  useEffect(stop, [pick])
  const playScale = () => {
    if (running !== null) return stop()
    stop()
    playChord(SCALE_RUN.map((st) => stepKey(key, st)), { gap: NOTE_GAP })
    SCALE_RUN.forEach((_, i) => timers.current.push(window.setTimeout(() => setRunning(i), 20 + i * NOTE_GAP * 1000)))
    timers.current.push(window.setTimeout(() => setRunning(null), 20 + SCALE_RUN.length * NOTE_GAP * 1000 + 300))
  }
  const step = running !== null ? SCALE_RUN[running] : hover
  const shown = step !== null ? key.chords[step % 7] : null

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
          <button className={`pill-btn ${running !== null ? 'accent' : ''}`} onClick={playScale}>
            {running !== null ? 'Stop' : 'Play the Scale'}
          </button>
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
      {peek && <ChordPeek peek={peek} />}
    </main>
  )
}
