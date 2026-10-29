import { useMemo, useState } from 'react'
import type { Backend, ChordLevel, SeparationMode } from '../api'
import { desktop, isMac } from '../platform'
import { REPOSITORY_NAME, checkForUpdates, installUpdate, progressText, saveToken, useUpdates } from '../platform/updates'
import { errorMessage, updateSettings, useApp } from '../store'
import { FolderIcon } from './Icons'

export function Profile() {
  const songs = useApp((s) => s.songs)
  const settings = useApp((s) => s.settings)
  const caps = useApp((s) => s.capabilities)
  const engine = useApp((s) => s.engine)
  const hasDemucs = !!caps?.backends.includes('demucs')

  const stats = useMemo(() => {
    const ready = (songs ?? []).filter((s) => s.status === 'ready')
    const minutes = Math.round(ready.reduce((t, s) => t + (s.duration ?? 0), 0) / 60)
    const counts = new Map<string, number>()
    for (const s of ready) if (s.key) counts.set(s.key, (counts.get(s.key) ?? 0) + 1)
    const top = [...counts].sort((a, b) => b[1] - a[1])[0]?.[0] ?? '–'
    const bpms = ready.map((s) => s.bpm ?? 0).filter(Boolean)
    const avg = bpms.length ? Math.round(bpms.reduce((a, b) => a + b, 0) / bpms.length) : null
    return { count: songs?.length ?? 0, minutes, top, avg }
  }, [songs])

  return (
    <main className="page profile">
      <h1 className="page-title">Profile</h1>

      <section className="panel">
        <h2>Your library</h2>
        <div className="profile-stats">
          <Big value={String(stats.count)} label={stats.count === 1 ? 'song' : 'songs'} />
          <Big value={String(stats.minutes)} label="minutes of music" />
          <Big value={stats.top} label="most common key" />
          <Big value={stats.avg ? String(stats.avg) : '–'} label="average BPM" />
        </div>
        {desktop && engine && (
          <div className="row folder">
            <FolderIcon />
            <span className="path" title={engine.libraryPath}>
              {engine.libraryPath}
            </span>
            <button onClick={() => void desktop!.reveal()}>{isMac ? 'Show in Finder' : 'Show in Explorer'}</button>
          </div>
        )}
      </section>

      <section className="panel">
        <h2>New songs</h2>
        <div className="settings">
          <label>
            Separate into
            <select value={settings.mode} onChange={(e) => updateSettings({ mode: e.target.value as SeparationMode })}>
              <option value="4stems">Vocals · Drums · Bass · Other</option>
              <option value="2stems">Vocals · Accompaniment</option>
              <option value="6stems" disabled={!hasDemucs}>
                6 stems (+ Guitar · Piano){hasDemucs ? '' : ' - needs Demucs'}
              </option>
              <option value="none">No separation</option>
            </select>
          </label>
          <label>
            Separation engine
            <select value={settings.backend} onChange={(e) => updateSettings({ backend: e.target.value as Backend })}>
              <option value="auto">Best available</option>
              <option value="demucs" disabled={!hasDemucs}>
                Demucs (neural){hasDemucs ? '' : ' - not installed'}
              </option>
              <option value="dsp">Fast (DSP)</option>
            </select>
          </label>
          <label>
            Chord detail
            <select value={settings.chordLevel} onChange={(e) => updateSettings({ chordLevel: e.target.value as ChordLevel })}>
              <option value="basic">Basic (major and minor)</option>
              <option value="intermediate">Intermediate (+ sevenths)</option>
              <option value="advanced">Advanced (+ dim, aug, sus)</option>
            </select>
          </label>
        </div>
        <p className="hint">
          {hasDemucs
            ? 'Stems are separated with Demucs, a neural network: the cleanest results, but it takes a while for each song.'
            : 'Stems are separated with the fast built-in separator. It’s good for turning parts down to practise along, not for clean isolation. Running KeyFinder from source with Demucs installed gives studio-quality stems.'}
        </p>
      </section>

      {desktop && <EngineSection />}
      {desktop && <UpdatesSection />}

      <section className="panel">
        <h2>About</h2>
        <p className="hint">
          KeyFinder {caps?.version ?? ''} · key, tempo and chord detection, stem separation, pitch and speed for practising.
          {caps ? ` Pitch shifting: ${caps.rubberband ? 'Rubber Band (formant-preserving)' : 'FFmpeg'}.` : ''}
        </p>
      </section>
    </main>
  )
}

function Big({ value, label }: { value: string; label: string }) {
  return (
    <div>
      <span className="big">{value}</span>
      <span className="muted">{label}</span>
    </div>
  )
}

function EngineSection() {
  const engine = useApp((s) => s.engine)
  if (!engine || engine.status === 'ready') return null
  return (
    <section className="panel">
      <h2>Engine</h2>
      <p className={engine.status === 'failed' ? 'error' : 'hint'}>
        {engine.status === 'failed' ? 'The analysis engine isn’t running.' : 'The analysis engine is starting…'}
      </p>
      {engine.error && <pre className="log">{engine.error}</pre>}
      {engine.status === 'failed' && <button onClick={() => void desktop!.engine.restart()}>Restart Engine</button>}
    </section>
  )
}

function UpdatesSection() {
  const u = useUpdates()
  const [token, setToken] = useState('')
  const [error, setError] = useState<string | null>(null)
  return (
    <section className="panel">
      <h2>Updates</h2>
      <p className="hint">KeyFinder {u.version ?? ''}</p>
      {u.blocker === 'translocated' && (
        <p className="error">
          macOS is running KeyFinder from a temporary copy, so it can’t update itself. Move it to Applications, run{' '}
          <code>xattr -dr com.apple.quarantine /Applications/KeyFinder.app</code> in Terminal once, and open it again.
        </p>
      )}
      {u.hasToken === false ? (
        <form
          className="row wrap"
          onSubmit={async (e) => {
            e.preventDefault()
            setError(null)
            try {
              await saveToken(token)
              setToken('')
            } catch (err) {
              setError(errorMessage(err))
            }
          }}
        >
          <p className="hint">
            Updates come from the private {REPOSITORY_NAME} repository. Paste a fine-grained GitHub token with <b>Contents: Read-only</b> access
            to it; it’s kept on this computer only.
          </p>
          <input type="password" placeholder="github_pat_…" value={token} onChange={(e) => setToken(e.target.value)} aria-label="GitHub token" />
          <button className="pill-btn accent" disabled={!token.trim()}>
            Save Token
          </button>
        </form>
      ) : (
        <div className="row wrap">
          {u.status === 'available' && u.found ? (
            <>
              <span>
                KeyFinder <b>{u.found.version}</b> is ready to install.
              </span>
              <button className="pill-btn accent" onClick={() => void installUpdate()} disabled={!!u.blocker}>
                Install and Restart
              </button>
            </>
          ) : u.status === 'installing' ? (
            <span>Installing… {u.progress ? progressText(u.progress) : ''}</span>
          ) : (
            <>
              <span className="hint">
                {u.status === 'checking' ? 'Checking…' : u.status === 'none' ? 'KeyFinder is up to date.' : u.status === 'error' ? u.error : ''}
              </span>
              <button onClick={() => void checkForUpdates()} disabled={u.status === 'checking'}>
                Check for Updates
              </button>
            </>
          )}
        </div>
      )}
      {u.found?.notes && u.status === 'available' && <pre className="log">{u.found.notes}</pre>}
      {error && <p className="error">{error}</p>}
    </section>
  )
}
