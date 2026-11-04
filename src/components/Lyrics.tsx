import { useEffect, useMemo, useRef, useState } from 'react'
import { type Chord, type Song, editLyrics, findLyrics, getSong } from '../api'
import { chordIndexAt, chordLabel, lineIndexAt, placeChords } from '../music'
import { playback } from '../playback'
import { errorMessage, toast } from '../store'
import { useFrame } from './useFrame'

const WORKING = new Set(['queued', 'working'])

/**
 * The lyrics as a chord chart that follows the song: the chords over the words they change on,
 * the line being sung bright and kept in view, its words lighting up as they're sung, and the
 * chord playing now highlighted. Click a line to go there.
 */
export function LyricsPanel({ song, chords, semitones, flatsAt }: {
  song: Song
  chords: Chord[]
  semitones: number
  flatsAt: (t: number) => boolean
}) {
  const status = song.lyrics_status
  const lines = song.lyrics?.lines ?? []
  const rows = useMemo(() => placeChords(lines, chords), [lines, chords])
  const [line, setLine] = useState(-1)
  const [sung, setSung] = useState(-1) // words of the current line already sung
  const [chord, setChord] = useState(-1)
  const [editing, setEditing] = useState(false)
  const scroller = useRef<HTMLDivElement>(null)

  useFrame(() => {
    if (!lines.length) return
    const t = playback.time()
    const i = lineIndexAt(lines, t)
    if (i !== line) setLine(i)
    const words = i >= 0 ? lines[i].words : []
    let k = -1
    while (k + 1 < words.length && words[k + 1].start <= t) k++
    if (k !== sung) setSung(k)
    const c = chordIndexAt(chords, t)
    if (c !== chord) setChord(c)
  })

  // Keep the line being sung in the middle of the panel.
  useEffect(() => {
    const box = scroller.current
    const el = box?.querySelector<HTMLElement>(`[data-line="${line}"]`)
    if (!box || !el) return
    box.scrollTo({ top: el.offsetTop - box.clientHeight / 2 + el.clientHeight / 2, behavior: 'smooth' })
  }, [line])

  // While the lyrics are being found, check on them.
  useEffect(() => {
    if (!status || !WORKING.has(status)) return
    const timer = window.setInterval(async () => {
      try {
        const fresh = await getSong(song.id)
        if (fresh.lyrics_status !== status || fresh.lyrics_stage !== song.lyrics_stage || fresh.lyrics_progress !== song.lyrics_progress) {
          playback.refreshSong(fresh)
        }
      } catch {
        /* the engine is busy or restarting: try again next time */
      }
    }, 2000)
    return () => window.clearInterval(timer)
  }, [song.id, status, song.lyrics_stage, song.lyrics_progress])

  const find = async (mode?: 'auto' | 'online') => {
    try {
      await findLyrics(song.id, mode)
      playback.refreshSong(await getSong(song.id))
    } catch (e) {
      toast(errorMessage(e), true)
    }
  }

  const current = chords[chord]
  const label = (c: Chord) => chordLabel(c, semitones, flatsAt(c.start))

  return (
    <section className="panel lyrics">
      <div className="lyrics-head">
        <h2>Lyrics</h2>
        {status === 'ready' && !editing && (
          <div className="row">
            <button className="text-btn small" onClick={() => setEditing(true)}>
              Edit
            </button>
            <button className="text-btn small" onClick={() => void find()}>
              Find again
            </button>
          </div>
        )}
      </div>

      {status && WORKING.has(status) ? (
        <p className="hint">
          {song.lyrics_stage ?? 'Finding the lyrics'}
          {song.lyrics_progress ? ` · ${Math.round(song.lyrics_progress * 100)}%` : ''}…
        </p>
      ) : editing && song.lyrics ? (
        <LyricsEditor song={song} onDone={() => setEditing(false)} />
      ) : lines.length ? (
        <>
          <div className="lyrics-scroll" ref={scroller}>
            {rows.map((row, r) =>
              row.kind === 'break' ? (
                <p key={`b${r}`} className="lyric-break" onClick={() => playback.seek(row.start)}>
                  {row.chords.map((c, k) => (
                    <span key={k} className={`lyric-chord ${c === current ? 'now' : ''}`}>
                      {label(c)}
                    </span>
                  ))}
                </p>
              ) : (
                <p
                  key={`l${row.index}`}
                  data-line={row.index}
                  className={`lyric-line ${row.index === line ? 'current' : row.index < line ? 'past' : ''}`}
                  onClick={() => playback.seek(Math.max(0, row.start - 0.5))}
                >
                  {row.words.map((w, k) => (
                    <span key={k} className={`lyric-word ${row.index === line && k <= sung ? 'sung' : ''}`}>
                      <span className="lyric-chords">
                        {w.chords.map((c, j) => (
                          <span key={j} className={`lyric-chord ${c === current ? 'now' : ''}`}>
                            {label(c)}
                          </span>
                        ))}
                      </span>
                      <span className="lyric-text">{w.text}</span>
                    </span>
                  ))}
                </p>
              ),
            )}
          </div>
          <p className="hint lyrics-credit">
            {song.lyrics?.source === 'lrclib' ? (
              <>Lyrics from LRCLIB, timed to this recording.</>
            ) : song.lyrics?.source === 'edited' ? (
              <>Edited lyrics.</>
            ) : (
              <>Transcribed from the vocals; it can mishear a word. Use Edit to correct it.</>
            )}
            {song.lyrics_note ? ` ${song.lyrics_note.charAt(0).toUpperCase()}${song.lyrics_note.slice(1)}.` : ''}
          </p>
        </>
      ) : (
        <div className="lyrics-empty">
          <p className="hint">
            {status === 'none'
              ? `No lyrics found${song.lyrics_note ? `: ${song.lyrics_note}` : ''}.`
              : status === 'failed'
                ? `Couldn’t find the lyrics${song.lyrics_note ? `: ${song.lyrics_note}` : ''}.`
                : 'Find this song’s lyrics, with the chords over the words.'}
          </p>
          <button className="pill-btn" onClick={() => void find('auto')}>
            Find Lyrics
          </button>
        </div>
      )}
    </section>
  )
}

/** Correct the words line by line; an emptied line is removed. */
function LyricsEditor({ song, onDone }: { song: Song; onDone: () => void }) {
  const lines = song.lyrics!.lines
  const [texts, setTexts] = useState(() => lines.map((l) => l.words.map((w) => w.text).join(' ')))
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true)
    try {
      await editLyrics(song.id, texts)
      playback.refreshSong(await getSong(song.id))
      onDone()
    } catch (e) {
      toast(errorMessage(e), true)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="lyrics-editor">
      <div className="lyrics-scroll">
        {texts.map((t, i) => (
          <input
            key={i}
            value={t}
            aria-label={`Line ${i + 1}`}
            onChange={(e) => setTexts((all) => all.map((x, j) => (j === i ? e.target.value : x)))}
          />
        ))}
      </div>
      <p className="hint">Each line keeps its timing. Empty a line to remove it.</p>
      <div className="row">
        <button className="pill-btn accent" disabled={saving} onClick={() => void save()}>
          {saving ? 'Saving…' : 'Save'}
        </button>
        <button className="text-btn" onClick={onDone}>
          Cancel
        </button>
      </div>
    </div>
  )
}
