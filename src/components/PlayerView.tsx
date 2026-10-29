import { useEffect, useMemo, useRef, useState } from 'react'
import { type Chord, type ChordLevel, type Song, coverUrl, exportPath, saveFromApi } from '../api'
import { beatIndexAt, camelot, chordIndexAt, chordLabel, formatTime, keyUsesFlats, mod12, relativeKey, transposeKeyName } from '../music'
import { MAX_SPEED, MIN_SPEED, playback } from '../playback'
import { errorMessage, loadSong, navigate, toast, updateSettings, useApp } from '../store'
import { Back5Icon, ChevronLeftIcon, Forward5Icon, LibraryIcon, PauseIcon, PlayIcon } from './Icons'
import { useFrame } from './useFrame'
import { usePlayback } from './usePlayback'

const LEVELS: { key: ChordLevel; label: string }[] = [
  { key: 'basic', label: 'Basic' },
  { key: 'intermediate', label: 'Intermediate' },
  { key: 'advanced', label: 'Advanced' },
]

export function PlayerView({ songId }: { songId: string }) {
  const song = usePlayback((p) => p.song)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setError(null)
    loadSong(songId).catch((e) => setError(errorMessage(e)))
  }, [songId])

  if (error) {
    return (
      <main className="page player">
        <BackButton />
        <p className="empty">{error}</p>
      </main>
    )
  }
  if (!song || song.id !== songId || !song.analysis) {
    return (
      <main className="page player">
        <BackButton />
        <p className="empty">Loading…</p>
      </main>
    )
  }
  return <Player song={song} />
}

function BackButton() {
  return (
    <button className="icon-btn round back" aria-label="Back to library" onClick={() => navigate('library')}>
      <ChevronLeftIcon />
    </button>
  )
}

function Player({ song }: { song: Song }) {
  const a = song.analysis!
  const semitones = usePlayback((p) => p.semitones)
  const speed = usePlayback((p) => p.speed)
  const level = useApp((s) => s.settings.chordLevel)
  const cover = coverUrl(song)
  const tonic = a.key.tonic + semitones
  const flats = keyUsesFlats(tonic, a.key.mode)
  const chords = a.chords[level] ?? []

  return (
    <main className="page player">
      <div className="player-head">
        <BackButton />
        <span className="art large">{cover ? <img src={cover} alt="" /> : <LibraryIcon />}</span>
        <div className="player-titles">
          <h1>{song.title}</h1>
          <span className="muted">{song.artist || 'Unknown artist'}</span>
        </div>
      </div>

      <section className="stats">
        <Stat label="Key" value={transposeKeyName(a.key, semitones)} sub={semitones ? `original ${a.key.name}` : `${Math.round(a.key.confidence * 100)}% confidence`} />
        <Stat label="Camelot" value={camelot(tonic, a.key.mode)} sub={`relative ${relativeKey(tonic, a.key.mode)}`} />
        <Stat label="Tempo" value={(a.bpm * speed).toFixed(speed === 1 ? 1 : 0)} sub={speed === 1 ? 'BPM' : `BPM (original ${a.bpm})`} />
        <Stat label="Tuning" value={`${a.tuning_cents > 0 ? '+' : ''}${Math.round(a.tuning_cents)}`} sub="cents from A440" />
      </section>

      <NowPlaying song={song} chords={chords} semitones={semitones} flats={flats} />

      <div className="columns">
        <Mixer />
        <Practice song={song} />
      </div>
      <p className="shortcuts">
        <kbd>Space</kbd> play/pause · <kbd>←</kbd>/<kbd>→</kbd> 5 seconds · <kbd>[</kbd>/<kbd>]</kbd> pitch · <kbd>L</kbd> loop ·{' '}
        <kbd>M</kbd> metronome · drag across the waveform to loop
      </p>
    </main>
  )
}

function Stat({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="stat">
      <span className="label">{label}</span>
      <span className="value">{value}</span>
      <span className="sub">{sub}</span>
    </div>
  )
}

// ---------------------------------------------------------------- now playing

const PX_PER_SECOND = 80

function NowPlaying({ song, chords, semitones, flats }: { song: Song; chords: Chord[]; semitones: number; flats: boolean }) {
  const a = song.analysis!
  const playing = usePlayback((p) => p.playing || p.countingIn)
  const loading = usePlayback((p) => p.loading)
  const loop = usePlayback((p) => p.loop)
  const nowRef = useRef<HTMLSpanElement>(null)
  const nextRef = useRef<HTMLSpanElement>(null)
  const trackRef = useRef<HTMLDivElement>(null)
  const tickerRef = useRef<HTMLDivElement>(null)
  const dotsRef = useRef<HTMLDivElement>(null)
  const timeRef = useRef<HTMLSpanElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const last = useRef({ chord: -2, label: '' })
  const drag = useRef<{ start: number; moved: boolean } | null>(null)
  const duration = a.duration
  const firstDownbeat = useMemo(() => (a.downbeats.length ? a.beats.indexOf(a.downbeats[0]) : 0), [a])

  // Re-render the chord labels when the key or detail level changes.
  useEffect(() => {
    last.current.chord = -2
  }, [chords, semitones, flats])

  useFrame(() => {
    const t = playback.time()
    if (timeRef.current) timeRef.current.textContent = formatTime(t)
    if (trackRef.current && tickerRef.current) {
      trackRef.current.style.transform = `translateX(${tickerRef.current.clientWidth * 0.3 - t * PX_PER_SECOND}px)`
    }
    const i = chordIndexAt(chords, t)
    if (i !== last.current.chord) {
      last.current.chord = i
      trackRef.current?.querySelector('.chord.current')?.classList.remove('current')
      trackRef.current?.querySelector(`[data-index="${i}"]`)?.classList.add('current')
      if (nowRef.current) nowRef.current.textContent = i >= 0 ? chordLabel(chords[i], semitones, flats) : '–'
      const next = chords.slice(i + 1).find((c) => c.root !== null)
      if (nextRef.current) nextRef.current.textContent = next ? chordLabel(next, semitones, flats) : '–'
    }
    const b = beatIndexAt(a.beats, t)
    const pos = b >= 0 ? mod12(b - firstDownbeat) % 4 : -1
    const fresh = b >= 0 && t - a.beats[b] < 0.15 && playback.state.playing
    dotsRef.current?.querySelectorAll('i').forEach((dot, n) => dot.classList.toggle('on', fresh && n === pos))
    draw(t)
  })

  const draw = (t: number) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const dpr = window.devicePixelRatio || 1
    const w = canvas.clientWidth
    const h = canvas.clientHeight
    if (!w) return
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr)
      canvas.height = Math.round(h * dpr)
    }
    const g = canvas.getContext('2d')!
    g.setTransform(dpr, 0, 0, dpr, 0, 0)
    g.clearRect(0, 0, w, h)
    const css = getComputedStyle(canvas)
    const loopState = playback.state.loop
    if (loopState.a !== null) {
      const x0 = (loopState.a / duration) * w
      const x1 = loopState.b !== null ? (loopState.b / duration) * w : x0 + 2
      g.fillStyle = loopState.on ? css.getPropertyValue('--loop-on') : css.getPropertyValue('--loop-off')
      g.fillRect(x0, 0, Math.max(2, x1 - x0), h)
    }
    const peaks = a.waveform
    const played = (t / duration) * w
    const barW = w / peaks.length
    const playedColor = css.getPropertyValue('--wave-played')
    const restColor = css.getPropertyValue('--wave')
    for (let i = 0; i < peaks.length; i++) {
      const x = i * barW
      const ph = Math.max(1, peaks[i] * (h - 10))
      g.fillStyle = x < played ? playedColor : restColor
      g.fillRect(x, (h - ph) / 2, Math.max(1, barW - 0.6), ph)
    }
    g.fillStyle = css.getPropertyValue('--playhead')
    g.fillRect(played - 1, 0, 2, h)
  }

  const timeAt = (clientX: number) => {
    const r = canvasRef.current!.getBoundingClientRect()
    return Math.max(0, Math.min(1, (clientX - r.left) / r.width)) * duration
  }

  return (
    <section className="panel now-playing">
      <div className="chord-now">
        <div>
          <span className="label">Now</span>
          <span className="chord-big" ref={nowRef}>
            –
          </span>
        </div>
        <div>
          <span className="label">Next</span>
          <span className="chord-next" ref={nextRef}>
            –
          </span>
        </div>
        <div className="beat-dots" ref={dotsRef} aria-hidden>
          <i className="down" />
          <i />
          <i />
          <i />
        </div>
      </div>

      <div className="ticker" ref={tickerRef}>
        <div className="ticker-track" ref={trackRef} style={{ width: duration * PX_PER_SECOND }}>
          {chords.map((c, i) => (
            <button
              key={i}
              data-index={i}
              className={`chord ${c.root === null ? 'nc' : ''}`}
              style={{ left: c.start * PX_PER_SECOND, width: Math.max(2, (c.end - c.start) * PX_PER_SECOND - 3) }}
              onClick={() => playback.seek(c.start)}
              tabIndex={-1}
            >
              {chordLabel(c, semitones, flats)}
            </button>
          ))}
        </div>
        <div className="ticker-head" />
      </div>

      <canvas
        ref={canvasRef}
        className="waveform"
        aria-label="Waveform: click to seek, drag to set a loop"
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId)
          drag.current = { start: timeAt(e.clientX), moved: false }
        }}
        onPointerMove={(e) => {
          const d = drag.current
          if (!d) return
          const t = timeAt(e.clientX)
          if (Math.abs(t - d.start) > duration * 0.005) {
            d.moved = true
            playback.setLoop({ a: Math.min(d.start, t), b: Math.max(d.start, t), on: false })
          }
        }}
        onPointerUp={() => {
          const d = drag.current
          drag.current = null
          if (!d) return
          if (d.moved) {
            const { a: la, b: lb } = playback.state.loop
            const start = playback.snapToBeat(la!)
            playback.setLoop({ a: start, b: playback.snapToBeat(lb!), on: true })
            playback.seek(start)
          } else playback.seek(d.start)
        }}
      />

      <div className="transport">
        <span className="time" ref={timeRef}>
          0:00
        </span>
        <div className="transport-buttons">
          <button className="icon-btn" aria-label="Back 5 seconds" title="Back 5 s (←)" onClick={() => playback.seek(playback.time() - 5)}>
            <Back5Icon width={28} height={28} />
          </button>
          <button className="play" aria-label={playing ? 'Pause' : 'Play'} title="Play / pause (Space)" onClick={() => playback.toggle()} disabled={loading}>
            {playing ? <PauseIcon width={26} height={26} /> : <PlayIcon width={26} height={26} />}
          </button>
          <button className="icon-btn" aria-label="Forward 5 seconds" title="Forward 5 s (→)" onClick={() => playback.seek(playback.time() + 5)}>
            <Forward5Icon width={28} height={28} />
          </button>
        </div>
        <span className="time right">{formatTime(duration)}</span>
      </div>
      {loading && <span className="loading">Changing key… the first time takes a few seconds</span>}
      {loop.a !== null && loop.b !== null && (
        <span className="loop-info">
          Loop {formatTime(loop.a)} → {formatTime(loop.b)}
        </span>
      )}
    </section>
  )
}

// ---------------------------------------------------------------- mixer

function Mixer() {
  const tracks = usePlayback((p) => p.tracks)
  return (
    <section className="panel">
      <h2>Mixer</h2>
      {tracks.map((t) => (
        <div className="stem" key={t.name}>
          <span className="name">{t.name === 'original' ? 'Song' : t.name}</span>
          <button className={`toggle mute ${t.muted ? 'on' : ''}`} title={`Mute ${t.name}`} onClick={() => playback.setTrack(t.name, { muted: !t.muted })}>
            M
          </button>
          <button className={`toggle solo ${t.solo ? 'on' : ''}`} title={`Solo ${t.name}`} onClick={() => playback.setTrack(t.name, { solo: !t.solo })}>
            S
          </button>
          <input
            type="range"
            min={0}
            max={1.5}
            step={0.01}
            value={t.volume}
            aria-label={`${t.name} volume`}
            onChange={(e) => playback.setTrack(t.name, { volume: Number(e.target.value) })}
            onDoubleClick={() => playback.setTrack(t.name, { volume: 1 })}
          />
        </div>
      ))}
      {tracks.length === 1 && <p className="hint">This song wasn’t split into stems. Add it again with separation on to mix vocals, drums and bass.</p>}
    </section>
  )
}

// ---------------------------------------------------------------- practice

function Practice({ song }: { song: Song }) {
  const semitones = usePlayback((p) => p.semitones)
  const speed = usePlayback((p) => p.speed)
  const metronome = usePlayback((p) => p.metronome)
  const metronomeVolume = usePlayback((p) => p.metronomeVolume)
  const countIn = usePlayback((p) => p.countIn)
  const loop = usePlayback((p) => p.loop)
  const level = useApp((s) => s.settings.chordLevel)
  const [format, setFormat] = useState<'mp3' | 'wav' | 'm4a'>('mp3')
  const [exporting, setExporting] = useState(false)

  const exportMix = async () => {
    setExporting(true)
    const gains = playback.effectiveGains()
    const parts = [
      semitones ? `${semitones > 0 ? '+' : ''}${semitones}` : '',
      speed !== 1 ? `${Math.round(speed * 100)}%` : '',
      ...Object.entries(gains)
        .filter(([, v]) => v === 0)
        .map(([k]) => `no ${k}`),
    ].filter(Boolean)
    const name = `${song.title}${parts.length ? ` (${parts.join(', ')})` : ''}.${format}`
    try {
      const saved = await saveFromApi(exportPath(song.id, { semitones, speed, volumes: gains, format }), name)
      if (saved) toast(`Exported ${name}`)
    } catch (e) {
      toast(errorMessage(e), true)
    } finally {
      setExporting(false)
    }
  }

  return (
    <section className="panel controls">
      <h2>Practice</h2>
      <div className="control">
        <span className="label">Pitch</span>
        <div className="stepper">
          <button aria-label="Pitch down" onClick={() => void playback.setPitch(semitones - 1)}>
            −
          </button>
          <output>{semitones > 0 ? `+${semitones}` : semitones}</output>
          <button aria-label="Pitch up" onClick={() => void playback.setPitch(semitones + 1)}>
            +
          </button>
          <button className="text-btn small" disabled={!semitones} onClick={() => void playback.setPitch(0)}>
            Reset
          </button>
        </div>
      </div>
      <div className="control">
        <label className="label" htmlFor="speed">
          Speed <output>{Math.round(speed * 100)}%</output>
        </label>
        <div className="row">
          <input id="speed" type="range" min={MIN_SPEED} max={MAX_SPEED} step={0.05} value={speed} onChange={(e) => playback.setSpeed(Number(e.target.value))} />
          <button className="text-btn small" disabled={speed === 1} onClick={() => playback.setSpeed(1)}>
            Reset
          </button>
        </div>
      </div>
      <div className="control">
        <span className="label">Chords</span>
        <div className="segmented" role="radiogroup" aria-label="Chord detail">
          {LEVELS.map((l) => (
            <button key={l.key} role="radio" aria-checked={level === l.key} className={level === l.key ? 'active' : ''} onClick={() => updateSettings({ chordLevel: l.key })}>
              {l.label}
            </button>
          ))}
        </div>
      </div>
      <div className="control row">
        <Switch checked={metronome} onChange={(v) => playback.setMetronome(v)} label="Metronome" />
        <input type="range" min={0} max={1} step={0.05} value={metronomeVolume} aria-label="Metronome volume" onChange={(e) => playback.setMetronomeVolume(Number(e.target.value))} />
      </div>
      <div className="control row">
        <Switch checked={countIn} onChange={(v) => playback.setCountIn(v)} label="Count-in (1 bar)" />
      </div>
      <div className="control">
        <span className="label">Loop</span>
        <div className="row wrap">
          <button onClick={() => playback.setLoopPoint('a')}>Set A</button>
          <button onClick={() => playback.setLoopPoint('b')}>Set B</button>
          <Switch checked={loop.on} disabled={loop.a === null || loop.b === null} onChange={() => playback.toggleLoop()} label="Loop" />
          <button className="text-btn small" disabled={loop.a === null && loop.b === null} onClick={() => playback.setLoop({ a: null, b: null, on: false })}>
            Clear
          </button>
        </div>
      </div>
      <div className="control">
        <span className="label">Export</span>
        <div className="row">
          <select value={format} onChange={(e) => setFormat(e.target.value as typeof format)} aria-label="Export format">
            <option value="mp3">MP3</option>
            <option value="wav">WAV</option>
            <option value="m4a">M4A</option>
          </select>
          <button className="pill-btn accent" disabled={exporting} onClick={() => void exportMix()}>
            {exporting ? 'Rendering…' : 'Export Mix…'}
          </button>
        </div>
        <span className="hint">Uses the mixer, pitch and speed you hear now.</span>
      </div>
    </section>
  )
}

function Switch({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <label className={`switch ${disabled ? 'disabled' : ''}`}>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span aria-hidden />
      {label}
    </label>
  )
}
