import { useEffect, useMemo, useState } from 'react'
import { type Backend, type ChordLevel, type LyricsMode, type SeparationMode, downloadDemucs, downloadLyricsModel } from '../api'
import { desktop, isMac } from '../platform'
import {
  REPOSITORY_NAME,
  checkForUpdates,
  discardPackage,
  dismissResult,
  installPackage,
  installUpdate,
  pickPackage,
  progressText,
  revertUpdate,
  saveToken,
  useUpdates,
} from '../platform/updates'
import { confirmDialog } from './Ask'
import { errorMessage, loadCapabilities, toast, updateSettings, useApp } from '../store'
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
          <label>
            Lyrics
            <select value={settings.lyrics} onChange={(e) => updateSettings({ lyrics: e.target.value as LyricsMode })}>
              <option value="auto">Look up online, else transcribe</option>
              <option value="online">Look up online only</option>
              <option value="off">Off</option>
            </select>
          </label>
        </div>
        {!hasDemucs && (
          <p className="hint">
            Stems are separated with the fast built-in separator: good for turning parts down to practise along, not for clean
            isolation. Install Demucs (<code>pip install -e ".[ml]"</code>) for studio-quality stems.
          </p>
        )}
      </section>

      {hasDemucs && <DemucsSection />}
      <LyricsSection />

      {desktop && <EngineSection />}
      {desktop && <UpdatesSection />}
      {desktop && <CopySection />}

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

const DEVICES: Record<string, string> = {
  mps: 'the Apple silicon GPU',
  cuda: 'the NVIDIA GPU',
  cpu: 'the CPU',
}

const DEMUCS_MODELS = [
  { name: 'htdemucs', label: '4-stem model', use: 'vocals, drums, bass, other (and 2 stems)' },
  { name: 'htdemucs_6s', label: '6-stem model', use: 'adds guitar and piano' },
]

function LyricsSection() {
  const status = useApp((s) => s.capabilities?.lyrics)
  const downloading = !!status?.downloading

  // Follow a download while it runs.
  useEffect(() => {
    if (!downloading) return
    const timer = window.setInterval(() => void loadCapabilities(), 1000)
    return () => window.clearInterval(timer)
  }, [downloading])

  return (
    <section className="panel">
      <h2>Lyrics</h2>
      <p className="hint">
        KeyFinder looks each song up on <b>LRCLIB</b>, a free lyrics database, by its title, artist and length (it sends
        those, nothing else). When LRCLIB doesn’t have it, <b>Whisper</b> transcribes the vocals on this computer.
        {status?.installed ? '' : ' Transcription isn’t installed in this engine, so only LRCLIB is used.'}
      </p>
      {status?.installed && (
        <div className="models">
          <div className="row model">
            <span className="model-name">
              <b>Whisper ({status.model})</b>
              <span className="muted">About {((status.size_mb ?? 0) / 1000).toFixed(1)} GB, downloaded once, the first time it’s needed</span>
            </span>
            {status.downloaded ? (
              <span className="ready">✓ Downloaded</span>
            ) : downloading ? (
              <span className="muted">Downloading…</span>
            ) : (
              <button
                onClick={async () => {
                  try {
                    await downloadLyricsModel()
                    await loadCapabilities()
                  } catch (e) {
                    toast(errorMessage(e), true)
                  }
                }}
              >
                Download
              </button>
            )}
          </div>
        </div>
      )}
      {status?.download_error && <p className="error">{status.download_error}</p>}
    </section>
  )
}

function DemucsSection() {
  const demucs = useApp((s) => s.capabilities?.demucs)
  const downloading = demucs?.downloading ?? null

  // Follow a download while it runs.
  useEffect(() => {
    if (!downloading) return
    const timer = window.setInterval(() => void loadCapabilities(), 1000)
    return () => window.clearInterval(timer)
  }, [downloading])

  if (!demucs?.installed) return null
  const device = DEVICES[demucs.device ?? 'cpu'] ?? demucs.device
  return (
    <section className="panel">
      <h2>Stem separation</h2>
      <p className="hint">
        Stems are separated with <b>Demucs</b>, a neural network from Meta AI, running on {device}.
        {demucs.device === 'cpu' ? ' On the CPU, allow a few minutes per song.' : ''} Each model
        is downloaded once, the first time it’s needed, or now:
      </p>
      <div className="models">
        {DEMUCS_MODELS.map((m) => {
          const ready = demucs.models?.[m.name]
          return (
            <div className="row model" key={m.name}>
              <span className="model-name">
                <b>{m.label}</b>
                <span className="muted">{m.use}</span>
              </span>
              {ready ? (
                <span className="ready">✓ Downloaded</span>
              ) : downloading === m.name ? (
                <span className="muted">Downloading…</span>
              ) : (
                <button
                  disabled={!!downloading}
                  onClick={async () => {
                    try {
                      await downloadDemucs(m.name)
                      await loadCapabilities()
                    } catch (e) {
                      toast(errorMessage(e), true)
                    }
                  }}
                >
                  Download
                </button>
              )}
            </div>
          )
        })}
      </div>
      {demucs.download_error && <p className="error">{demucs.download_error}</p>}
    </section>
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

const ARCH: Record<string, string> = { arm64: 'Apple silicon', x64: 'Intel' }

/** Save a copy of KeyFinder itself, to give to someone or take to another computer. */
function CopySection() {
  const [info, setInfo] = useState<{ formats: ('dmg' | 'zip')[]; blocker: string | null; arch: string } | null>(null)
  const [busy, setBusy] = useState<'dmg' | 'zip' | null>(null)
  const version = useApp((s) => s.capabilities?.version)

  useEffect(() => {
    void desktop!.copy.info().then(setInfo)
  }, [])

  if (!info?.formats.length) return null
  const forWhom = isMac ? `${ARCH[info.arch] ?? info.arch} Macs` : 'Windows (64-bit)'
  const save = async (format: 'dmg' | 'zip') => {
    setBusy(format)
    try {
      const saved = await desktop!.copy.save(format)
      if (saved) toast(`Saved ${saved.split(/[\\/]/).pop()}`)
    } catch (e) {
      toast(errorMessage(e), true)
    } finally {
      setBusy(null)
    }
  }
  return (
    <section className="panel" id="save-copy">
      <h2>Share KeyFinder</h2>
      <p className="hint">
        Save a copy of KeyFinder {version ?? ''} to give to someone or to install on another computer. It’s the app only: your
        library, settings and downloaded models stay here. It runs on {forWhom}
        {isMac ? '' : '; unzip it anywhere and open KeyFinder.exe'}. The first time it’s opened,{' '}
        {isMac ? 'right-click it and choose Open' : 'choose More info ▸ Run anyway if SmartScreen asks'}, as for a download from Releases.
      </p>
      {info.blocker === 'development' ? (
        <p className="hint">Only the installed app can save a copy of itself, not KeyFinder running from source.</p>
      ) : (
        <div className="row wrap">
          {info.formats.map((f) => (
            <button key={f} className={f === info.formats[0] ? 'pill-btn accent' : 'pill-btn'} disabled={!!busy} onClick={() => void save(f)}>
              {busy === f ? (f === 'dmg' ? 'Making the disk image…' : 'Zipping…') : f === 'dmg' ? 'Save as Disk Image (.dmg)…' : 'Save as ZIP…'}
            </button>
          ))}
        </div>
      )}
      {busy && <p className="hint">This takes a minute or two. The copy is about 400 MB: most of it is the analysis engine, Demucs and Whisper.</p>}
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
      {/* Not needed while the repository is public; for a private one, or more checks an hour. */}
      <details className="update-token">
        <summary>GitHub token (optional){u.hasToken ? ': saved' : ''}</summary>
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
            Updates come from the {REPOSITORY_NAME} repository on GitHub, which is public, so no token is needed. If it becomes private, or
            GitHub limits checks without one, paste a fine-grained token with <b>Contents: Read-only</b> access to it; it’s kept on this
            computer only.
          </p>
          <input type="password" placeholder="github_pat_…" value={token} onChange={(e) => setToken(e.target.value)} aria-label="GitHub token" />
          <button className="pill-btn" disabled={!token.trim()}>
            Save Token
          </button>
          {u.hasToken && (
            <button
              type="button"
              className="text-btn"
              onClick={async () => {
                setError(null)
                try {
                  await saveToken('')
                } catch (err) {
                  setError(errorMessage(err))
                }
              }}
            >
              Remove Token
            </button>
          )}
        </form>
      </details>
      {u.found?.notes && u.status === 'available' && <pre className="log">{u.found.notes}</pre>}
      {error && <p className="error">{error}</p>}
      <PackageUpdates />
    </section>
  )
}

const KIND_TEXT = {
  interface: 'a new interface; the analysis engine you have is kept',
  app: 'the whole app',
  installer: 'the Windows installer',
}

/**
 * Updating from a zip package (when GitHub can't be reached, say), and going back to the version
 * kept from before the last update. Neither touches the library or settings.
 */
function PackageUpdates() {
  const u = useUpdates()
  const [invalid, setInvalid] = useState<string | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  const [opening, setOpening] = useState(false)
  const p = u.pkg
  const blocked = !!u.packageBlocker

  const open = async () => {
    setInvalid(null)
    setFailed(null)
    setOpening(true)
    try {
      await pickPackage()
    } catch (e) {
      setInvalid(errorMessage(e))
    } finally {
      setOpening(false)
    }
  }
  const install = async () => {
    setFailed(null)
    try {
      await installPackage()
    } catch (e) {
      setFailed(errorMessage(e))
    }
  }
  const goBack = async () => {
    if (!u.previous) return
    const ok = await confirmDialog({
      title: `Go back to KeyFinder ${u.previous.version}?`,
      message: `KeyFinder restarts as ${u.previous.version}. ${u.version ?? 'This version'} is kept, so you can come back to it here. Your library and settings stay as they are.`,
      confirmLabel: 'Go Back and Restart',
    })
    if (!ok) return
    setFailed(null)
    try {
      await revertUpdate()
    } catch (e) {
      setFailed(errorMessage(e))
    }
  }

  return (
    <div className="update-packages">
      {u.result && (
        <div className={`update-result ${u.result.ok ? '' : 'error'}`} role="status">
          <span>
            {u.result.ok
              ? u.result.action === 'revert'
                ? `Went back to KeyFinder ${u.result.version}.`
                : `Updated to KeyFinder ${u.result.version}.${u.result.message ? ` ${u.result.message}` : ''}`
              : `${u.result.action === 'revert' ? 'Going back' : 'The update'} didn’t work: ${u.result.message}`}
          </span>
          <button className="text-btn small" onClick={dismissResult}>
            OK
          </button>
        </div>
      )}

      <h3>From a Package</h3>
      <p className="hint">
        Install an update from a .zip package: an interface update (made with <code>npm run update-package</code>) or a release’s app zip. The
        version you have now is kept, so you can go back to it. Your library and settings aren’t touched.
      </p>
      {u.packageBlocker === 'translocated' && <p className="error">Move KeyFinder to Applications first (see above).</p>}
      {!p ? (
        <div className="row wrap">
          <button className="pill-btn" onClick={() => void open()} disabled={blocked || opening || !!u.restarting}>
            {opening ? 'Checking…' : 'Install from Zip…'}
          </button>
          {u.packageBlocker === 'development' && <span className="hint">Packages install only in the packaged app.</span>}
        </div>
      ) : (
        <div className="update-package">
          <div>
            <b>KeyFinder {p.version}</b> <span className="muted">· {KIND_TEXT[p.kind]}</span>
          </div>
          <div className="muted">{p.file}</div>
          <div className={p.signed ? 'ok' : 'warn'}>
            {p.signed
              ? '✓ Signed with KeyFinder’s release key.'
              : 'Not signed with KeyFinder’s release key: install it only if you know where it came from.'}
          </div>
          {p.compared !== 'newer' && (
            <div className="warn">
              {p.compared === 'same' ? `You already have ${p.current}; this installs it again.` : `This is older than ${p.current}, the version you have.`}
            </div>
          )}
          {p.warning && <div className="warn">{p.warning}</div>}
          {p.notes && <pre className="log">{p.notes}</pre>}
          <div className="row wrap">
            <button className="pill-btn accent" onClick={() => void install()} disabled={!!u.restarting}>
              {u.restarting === 'package' ? 'Restarting…' : p.signed && p.compared === 'newer' ? 'Install and Restart' : 'Install Anyway and Restart'}
            </button>
            <button className="pill-btn" onClick={() => void discardPackage()} disabled={!!u.restarting}>
              Cancel
            </button>
          </div>
        </div>
      )}
      {invalid && (
        <div className="error zip-invalid" role="alert">
          <b>Zip File Invalid</b>
          <span>{invalid}</span>
        </div>
      )}

      <h3>Previous Version</h3>
      {u.previous ? (
        <div className="row wrap">
          <span className="hint">
            KeyFinder <b>{u.previous.version}</b> is kept from before the last update ({new Date(u.previous.savedAt).toLocaleDateString()}).
          </span>
          <button className="pill-btn" onClick={() => void goBack()} disabled={!!u.restarting || !!u.packageBlocker}>
            {u.restarting === 'revert' ? 'Restarting…' : `Go Back to ${u.previous.version}`}
          </button>
        </div>
      ) : (
        <p className="hint">None kept yet: the next update keeps the version it replaces, so you can go back to it here.</p>
      )}
      {failed && <p className="error">{failed}</p>}
    </div>
  )
}
