import { useEffect, useRef, useState } from 'react'
import {
  TRANSPOSE_FORMATS,
  type TransposeFormat,
  type TransposeItem,
  addTransposeFile,
  addTransposePaths,
  apiUrl,
  deleteTranspose,
  saveFromApi,
  saveManyFromApi,
  transposePath,
} from '../api'
import { formatTime, keyName } from '../music'
import { desktop } from '../platform'
import { errorMessage, toast } from '../store'

interface Entry {
  key: number
  name: string
  item: TransposeItem | null
  error: string | null
  semitones: number
}

// The list outlives the page, so leaving to look something up doesn't lose it.
let entries: Entry[] = []
let speed = 1
let format: TransposeFormat = 'mp3'
let seq = 0
const listeners = new Set<() => void>()
const changed = () => listeners.forEach((l) => l())

function useTranspose() {
  const [, bump] = useState(0)
  useEffect(() => {
    const l = () => bump((n) => n + 1)
    listeners.add(l)
    return () => void listeners.delete(l)
  }, [])
  return { entries, speed, format }
}

function update(key: number, patch: Partial<Entry>) {
  entries = entries.map((e) => (e.key === key ? { ...e, ...patch } : e))
  changed()
}

/** Adds files (a browser's File objects) to transpose. */
export async function addTransposeFiles(files: File[]) {
  if (desktop) {
    const paths = files.map((f) => desktop!.pathForFile(f)).filter(Boolean)
    if (paths.length) return addPaths(paths)
  }
  for (const f of files) {
    const key = ++seq
    entries = [...entries, { key, name: f.name, item: null, error: null, semitones: 0 }]
    changed()
    try {
      update(key, { item: await addTransposeFile(f) })
    } catch (e) {
      update(key, { error: errorMessage(e) })
    }
  }
}

async function addPaths(paths: string[]) {
  for (const p of paths) {
    const key = ++seq
    entries = [...entries, { key, name: p.split(/[\\/]/).pop() ?? p, item: null, error: null, semitones: 0 }]
    changed()
    try {
      const res = await addTransposePaths([p])
      if (res.created[0]) update(key, { item: res.created[0] })
      else update(key, { error: res.failed[0]?.error ?? 'couldn’t read it' })
    } catch (e) {
      update(key, { error: errorMessage(e) })
    }
  }
}

/** The file name a transposed file is saved under: "Song (E major, 90%).mp3". */
function savedName(item: TransposeItem, semitones: number) {
  const parts = [keyName(item.key.tonic + semitones, item.key.mode)]
  if (speed !== 1) parts.push(`${Math.round(speed * 100)}%`)
  return `${item.name} (${parts.join(', ')}).${format}`
}

const offset = (n: number) => (n > 0 ? `+${n}` : n < 0 ? `−${-n}` : '±0')

/**
 * Transpose audio files: change their key (and speed, for all of them) and save them, without
 * adding them to the library. Each file's key is found first, so the new key can be picked by name.
 */
export function Transpose() {
  const t = useTranspose()
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState<number | 'all' | null>(null)
  const [preview, setPreview] = useState<{ key: number; url: string; semitones: number } | null>(null)
  const player = useRef<HTMLAudioElement>(null)

  const pick = async () => {
    if (desktop) {
      const paths = await desktop.pickFiles('file')
      if (paths.length) await addPaths(paths)
    } else input.current?.click()
  }

  const save = async (e: Entry) => {
    if (!e.item) return
    setBusy(e.key)
    try {
      const saved = await saveFromApi(transposePath(e.item.id, e.semitones, speed, format), savedName(e.item, e.semitones))
      if (saved) toast(`Saved ${savedName(e.item, e.semitones)}`)
    } catch (err) {
      toast(errorMessage(err), true)
    } finally {
      setBusy(null)
    }
  }

  const saveAll = async () => {
    const ready = t.entries.filter((e) => e.item)
    if (!ready.length) return
    setBusy('all')
    try {
      const folder = await saveManyFromApi(
        ready.map((e) => ({ apiPath: transposePath(e.item!.id, e.semitones, speed, format), name: savedName(e.item!, e.semitones) })),
      )
      if (folder) toast(`Saved ${ready.length} file${ready.length === 1 ? '' : 's'}`)
    } catch (err) {
      toast(errorMessage(err), true)
    } finally {
      setBusy(null)
    }
  }

  const listen = async (e: Entry) => {
    if (!e.item) return
    if (preview?.key === e.key && preview.semitones === e.semitones && player.current) {
      player.current.paused ? void player.current.play() : player.current.pause()
      return
    }
    setBusy(e.key)
    try {
      const res = await fetch(apiUrl(transposePath(e.item.id, e.semitones, speed, 'mp3')))
      if (!res.ok) throw new Error(`Couldn’t make the preview (${res.status})`)
      if (preview) URL.revokeObjectURL(preview.url)
      const url = URL.createObjectURL(await res.blob())
      setPreview({ key: e.key, url, semitones: e.semitones })
      window.setTimeout(() => void player.current?.play(), 50)
    } catch (err) {
      toast(errorMessage(err), true)
    } finally {
      setBusy(null)
    }
  }

  const remove = (e: Entry) => {
    entries = entries.filter((x) => x.key !== e.key)
    changed()
    if (preview?.key === e.key) setPreview(null)
    if (e.item) void deleteTranspose(e.item.id).catch(() => {})
  }

  const ready = t.entries.filter((e) => e.item).length
  return (
    <main className="page transpose">
      <h1>Transpose</h1>
      <section className="panel">
        <p className="hint">
          Change the key of audio files, and their speed if you like, and save them: for a singer’s key, a capo-free guitar part, or a
          backing track. They aren’t added to your library. KeyFinder finds each file’s key first, so you can pick the new one by name.
          {desktop ? ' You can also drop files on this page.' : ''}
        </p>
        <div className="row wrap transpose-controls">
          <button className="pill-btn accent" onClick={() => void pick()}>
            Add Files…
          </button>
          <label>
            Speed <output>{Math.round(t.speed * 100)}%</output>
            <input type="range" min={0.5} max={1.5} step={0.05} value={t.speed} onChange={(e) => ((speed = Number(e.target.value)), changed())} />
          </label>
          <label>
            Save as
            <select value={t.format} onChange={(e) => ((format = e.target.value as TransposeFormat), changed())}>
              {TRANSPOSE_FORMATS.map((f) => (
                <option key={f} value={f}>
                  {f.toUpperCase()}
                </option>
              ))}
            </select>
          </label>
          {t.entries.length > 1 && (
            <button className="pill-btn" disabled={!ready || busy !== null} onClick={() => void saveAll()}>
              {busy === 'all' ? 'Saving…' : desktop ? `Save All ${ready} to a Folder…` : `Save All ${ready}`}
            </button>
          )}
        </div>
      </section>

      {t.entries.length > 0 && (
        <section className="panel transpose-list">
          {t.entries.map((e) => {
            const it = e.item
            return (
              <div key={e.key} className="transpose-row">
                <div className="transpose-file">
                  <b title={e.name}>{it?.name ?? e.name}</b>
                  <span className="muted">
                    {it
                      ? `${formatTime(it.duration)} · ${Math.round(it.bpm)} BPM${it.keys ? ` · keys ${it.keys.join(' → ')}` : ''}`
                      : e.error
                        ? ''
                        : 'Finding its key…'}
                  </span>
                  {e.error && <span className="error">{e.error}</span>}
                </div>
                {it && (
                  <>
                    <div className="transpose-key">
                      <span className="muted">{it.key.name}</span>
                      <span aria-hidden>→</span>
                      <select
                        aria-label="New key"
                        value={e.semitones}
                        onChange={(ev) => update(e.key, { semitones: Number(ev.target.value) })}
                      >
                        {Array.from({ length: 25 }, (_, i) => i - 12).map((n) => (
                          <option key={n} value={n}>
                            {keyName(it.key.tonic + n, it.key.mode)} ({offset(n)})
                          </option>
                        ))}
                      </select>
                      <div className="stepper">
                        <button aria-label="Down a semitone" disabled={e.semitones <= -12} onClick={() => update(e.key, { semitones: e.semitones - 1 })}>
                          −
                        </button>
                        <button aria-label="Up a semitone" disabled={e.semitones >= 12} onClick={() => update(e.key, { semitones: e.semitones + 1 })}>
                          +
                        </button>
                      </div>
                    </div>
                    <div className="row transpose-actions">
                      <button className="text-btn" disabled={busy !== null} onClick={() => void listen(e)}>
                        {busy === e.key ? 'Rendering…' : preview?.key === e.key && preview.semitones === e.semitones ? 'Play / Pause' : 'Listen'}
                      </button>
                      <button className="pill-btn" disabled={busy !== null} onClick={() => void save(e)}>
                        Save…
                      </button>
                    </div>
                  </>
                )}
                <button className="icon-btn transpose-remove" aria-label={`Remove ${e.name}`} title="Remove" onClick={() => remove(e)}>
                  ×
                </button>
              </div>
            )
          })}
          {preview && <audio ref={player} src={preview.url} controls className="transpose-preview" />}
        </section>
      )}
      <input
        ref={input}
        type="file"
        multiple
        accept="audio/*,video/*,.mp3,.wav,.flac,.m4a,.aac,.aif,.aiff,.ogg,.wma,.mp4,.mov"
        hidden
        onChange={(ev) => {
          const files = [...(ev.target.files ?? [])]
          ev.target.value = ''
          void addTransposeFiles(files)
        }}
      />
    </main>
  )
}
