// Plays a song's stems together, with a mixer, pitch, speed, A-B loop, metronome and count-in.
//
// Each stem is an <audio> element routed through Web Audio for its fader. Media elements give
// speed changes with the pitch kept (playbackRate + preservesPitch), which AudioBufferSourceNodes
// (Player's sample-synced engine) can't; the cost is a little drift, corrected every frame.
// Pitch can't be changed live, so transposed stems are rendered by the engine and swapped in.

import { type Song, apiUrl, stemPath } from './api'
import { beatIndexAt } from './music'

export interface TrackState {
  name: string
  volume: number
  muted: boolean
  solo: boolean
}

export interface LoopState {
  a: number | null
  b: number | null
  on: boolean
}

export interface PlaybackState {
  song: Song | null
  playing: boolean
  /** A count-in is clicking before playback starts. */
  countingIn: boolean
  /** Transposed stems are being rendered and loaded. */
  loading: boolean
  semitones: number
  speed: number
  tracks: TrackState[]
  loop: LoopState
  metronome: boolean
  metronomeVolume: number
  countIn: boolean
  error: string | null
}

interface Track extends TrackState {
  el: HTMLAudioElement
  gain: GainNode
}

const DRIFT = 0.05
export const MIN_SPEED = 0.5
export const MAX_SPEED = 1.5

class Playback {
  private ctx: AudioContext | null = null
  private tracks: Track[] = []
  private listeners = new Set<() => void>()
  private snapshot: PlaybackState
  private raf = 0
  private scheduler = 0
  private nextBeat = 0
  private countInTimer = 0
  private pitchPending: { t: number; wasPlaying: boolean } | null = null
  private endedListeners = new Set<() => void>()

  constructor() {
    this.snapshot = {
      song: null,
      playing: false,
      countingIn: false,
      loading: false,
      semitones: 0,
      speed: 1,
      tracks: [],
      loop: { a: null, b: null, on: false },
      metronome: false,
      metronomeVolume: 0.6,
      countIn: false,
      error: null,
    }
  }

  // ------------------------------------------------------------ state

  get state() {
    return this.snapshot
  }

  subscribe = (fn: () => void) => {
    this.listeners.add(fn)
    return () => {
      this.listeners.delete(fn)
    }
  }

  onEnded(fn: () => void) {
    this.endedListeners.add(fn)
    return () => {
      this.endedListeners.delete(fn)
    }
  }

  private set(patch: Partial<PlaybackState>) {
    this.snapshot = { ...this.snapshot, ...patch }
    this.listeners.forEach((fn) => fn())
  }

  private syncTracks() {
    this.set({ tracks: this.tracks.map(({ name, volume, muted, solo }) => ({ name, volume, muted, solo })) })
  }

  time() {
    return this.tracks[0]?.el.currentTime ?? 0
  }

  duration() {
    return this.snapshot.song?.analysis?.duration || this.tracks[0]?.el.duration || 0
  }

  // ------------------------------------------------------------ loading

  private context() {
    if (!this.ctx) this.ctx = new AudioContext()
    return this.ctx
  }

  load(song: Song) {
    if (this.snapshot.song?.id === song.id) return
    this.unload()
    const ctx = this.context()
    const stems = song.stems.filter((s) => s !== 'original')
    const names = stems.length ? stems : ['original']
    this.tracks = names.map((name) => {
      const el = new Audio()
      el.crossOrigin = 'anonymous'
      el.preload = 'auto'
      el.src = apiUrl(stemPath(song.id, name))
      const gain = ctx.createGain()
      ctx.createMediaElementSource(el).connect(gain).connect(ctx.destination)
      return { name, el, gain, volume: 1, muted: false, solo: false }
    })
    this.tracks[0].el.addEventListener('ended', () => {
      this.pause()
      this.endedListeners.forEach((fn) => fn())
    })
    this.set({ song, semitones: 0, loop: { a: null, b: null, on: false }, error: null, playing: false })
    this.syncTracks()
    this.applyRate()
    this.applyGains()
    this.raf = requestAnimationFrame(this.frame)
    this.scheduler = window.setInterval(this.scheduleClicks, 25)
  }

  unload() {
    this.pause()
    cancelAnimationFrame(this.raf)
    clearInterval(this.scheduler)
    for (const t of this.tracks) {
      t.el.pause()
      t.el.removeAttribute('src')
      t.el.load()
      t.gain.disconnect()
    }
    this.tracks = []
    this.pitchPending = null
    this.set({ song: null, tracks: [], playing: false, loading: false })
  }

  /** The analysis changed (e.g. the song was renamed): keep playing, show the new details. */
  refreshSong(song: Song) {
    if (this.snapshot.song?.id === song.id) this.set({ song })
  }

  // ------------------------------------------------------------ transport

  async play() {
    const song = this.snapshot.song
    if (!song || !this.tracks.length || this.snapshot.loading) return
    await this.context().resume()
    const { a, b, on } = this.snapshot.loop
    if (on && a !== null && b !== null) {
      const t = this.time()
      if (t < a || t >= b) this.seek(a)
    }
    if (this.snapshot.countIn && song.analysis?.bpm) {
      const beat = 60 / (song.analysis.bpm * this.snapshot.speed)
      const start = this.context().currentTime + 0.05
      for (let i = 0; i < 4; i++) this.click(start + i * beat, i === 0, true)
      this.set({ countingIn: true })
      this.countInTimer = window.setTimeout(() => void this.start(), (0.05 + 4 * beat) * 1000)
      return
    }
    await this.start()
  }

  private async start() {
    this.countInTimer = 0
    const t = this.time()
    for (const tr of this.tracks) tr.el.currentTime = t
    this.resetMetronome()
    try {
      await Promise.all(this.tracks.map((tr) => tr.el.play()))
      this.set({ playing: true, countingIn: false, error: null })
    } catch (e) {
      this.pause()
      this.set({ error: `Playback failed: ${(e as Error).message}` })
    }
  }

  pause() {
    clearTimeout(this.countInTimer)
    this.countInTimer = 0
    for (const tr of this.tracks) tr.el.pause()
    if (this.snapshot.playing || this.snapshot.countingIn) this.set({ playing: false, countingIn: false })
  }

  toggle() {
    if (this.snapshot.playing || this.snapshot.countingIn) this.pause()
    else void this.play()
  }

  seek(t: number) {
    if (!this.tracks.length) return
    const d = this.duration()
    t = Math.max(0, Math.min(t, d ? d - 0.05 : t))
    for (const tr of this.tracks) tr.el.currentTime = t
    this.resetMetronome()
  }

  // ------------------------------------------------------------ speed & pitch

  setSpeed(rate: number) {
    rate = Math.round(Math.max(MIN_SPEED, Math.min(MAX_SPEED, rate)) * 100) / 100
    this.set({ speed: rate })
    this.applyRate()
    this.resetMetronome()
  }

  private applyRate() {
    for (const tr of this.tracks) {
      tr.el.playbackRate = this.snapshot.speed
      tr.el.preservesPitch = true
    }
  }

  async setPitch(semitones: number) {
    const song = this.snapshot.song
    semitones = Math.max(-12, Math.min(12, Math.round(semitones)))
    if (!song || semitones === this.snapshot.semitones) return
    // A change during an earlier reload resumes from where playback was before that reload,
    // not from the half-loaded elements.
    if (!this.pitchPending) this.pitchPending = { t: this.time(), wasPlaying: this.snapshot.playing }
    const { t, wasPlaying } = this.pitchPending
    this.pause()
    this.set({ semitones, loading: true })
    try {
      // The engine renders transposed stems on first request (a few seconds per song).
      await Promise.all(
        this.tracks.map(
          (tr) =>
            new Promise<void>((resolve, reject) => {
              const done = () => {
                tr.el.removeEventListener('canplay', ok)
                tr.el.removeEventListener('error', fail)
              }
              const ok = () => (done(), resolve())
              const fail = () => (done(), reject(new Error(`Couldn’t load the ${tr.name} stem in the new key.`)))
              tr.el.addEventListener('canplay', ok)
              tr.el.addEventListener('error', fail)
              tr.el.src = apiUrl(stemPath(song.id, tr.name, semitones))
              tr.el.load()
            }),
        ),
      )
      if (this.snapshot.semitones !== semitones) return // superseded by a later change
      this.pitchPending = null
      this.applyRate() // a new source resets playbackRate
      this.seek(t)
      this.set({ loading: false })
      if (wasPlaying) await this.play()
    } catch (e) {
      if (this.snapshot.semitones !== semitones) return
      this.pitchPending = null
      this.set({ loading: false, error: (e as Error).message })
    }
  }

  // ------------------------------------------------------------ mixer

  setTrack(name: string, patch: Partial<Omit<TrackState, 'name'>>) {
    const tr = this.tracks.find((t) => t.name === name)
    if (!tr) return
    Object.assign(tr, patch)
    this.syncTracks()
    this.applyGains()
  }

  effectiveGain(t: TrackState) {
    const anySolo = this.tracks.some((x) => x.solo)
    if (anySolo) return t.solo ? t.volume : 0
    return t.muted ? 0 : t.volume
  }

  /** Each stem's level as heard now, for exporting the same mix. */
  effectiveGains() {
    return Object.fromEntries(this.tracks.map((t) => [t.name, this.effectiveGain(t)]))
  }

  private applyGains() {
    const ctx = this.ctx
    if (!ctx) return
    for (const tr of this.tracks) tr.gain.gain.setTargetAtTime(this.effectiveGain(tr), ctx.currentTime, 0.015)
  }

  // ------------------------------------------------------------ loop

  setLoop(loop: Partial<LoopState>) {
    const next = { ...this.snapshot.loop, ...loop }
    if (next.a !== null && next.b !== null && next.b < next.a) [next.a, next.b] = [next.b, next.a]
    if (next.a === null || next.b === null) next.on = false
    this.set({ loop: next })
  }

  setLoopPoint(which: 'a' | 'b') {
    const loop = { ...this.snapshot.loop, [which]: this.time() }
    this.setLoop({ ...loop, on: loop.a !== null && loop.b !== null })
  }

  toggleLoop() {
    const { a, b, on } = this.snapshot.loop
    if (a !== null && b !== null) this.setLoop({ on: !on })
  }

  /** Moves a time to the nearest beat when one is within a quarter second. */
  snapToBeat(t: number) {
    const beats = this.snapshot.song?.analysis?.beats ?? []
    const i = beatIndexAt(beats, t)
    const candidates = [beats[i], beats[i + 1]].filter((b): b is number => b !== undefined)
    const best = candidates.sort((x, y) => Math.abs(x - t) - Math.abs(y - t))[0]
    return best !== undefined && Math.abs(best - t) < 0.25 ? best : t
  }

  // ------------------------------------------------------------ metronome

  setMetronome(on: boolean) {
    this.set({ metronome: on })
    this.resetMetronome()
  }

  setMetronomeVolume(v: number) {
    this.set({ metronomeVolume: v })
  }

  setCountIn(on: boolean) {
    this.set({ countIn: on })
  }

  private resetMetronome() {
    const beats = this.snapshot.song?.analysis?.beats ?? []
    this.nextBeat = beatIndexAt(beats, this.time() - 0.01) + 1
  }

  /** Clicks on the song's detected beats (accented on downbeats), scheduled just ahead. */
  private scheduleClicks = () => {
    const a = this.snapshot.song?.analysis
    const ctx = this.ctx
    if (!this.snapshot.playing || !this.snapshot.metronome || !a || !ctx) return
    const t = this.time()
    const speed = this.snapshot.speed
    const downbeats = new Set(a.downbeats)
    while (this.nextBeat < a.beats.length) {
      const beat = a.beats[this.nextBeat]
      if (beat > t + 0.15 * speed) break
      const when = ctx.currentTime + (beat - t) / speed
      if (when >= ctx.currentTime - 0.01) this.click(Math.max(when, ctx.currentTime), downbeats.has(beat))
      this.nextBeat++
    }
  }

  private click(when: number, accent: boolean, force = false) {
    const ctx = this.context()
    const volume = force ? Math.max(this.snapshot.metronomeVolume, 0.5) : this.snapshot.metronomeVolume
    const osc = ctx.createOscillator()
    const env = ctx.createGain()
    osc.frequency.value = accent ? 1760 : 1175
    env.gain.setValueAtTime(0, when)
    env.gain.linearRampToValueAtTime(volume, when + 0.002)
    env.gain.exponentialRampToValueAtTime(0.0001, when + 0.06)
    osc.connect(env).connect(ctx.destination)
    osc.start(when)
    osc.stop(when + 0.08)
  }

  // ------------------------------------------------------------ frame loop

  private frame = () => {
    if (!this.tracks.length) return
    if (this.snapshot.playing) {
      const t = this.time()
      // Keep stems in step with the first one; media elements drift slightly.
      for (const tr of this.tracks.slice(1)) if (Math.abs(tr.el.currentTime - t) > DRIFT) tr.el.currentTime = t
      const { a, b, on } = this.snapshot.loop
      if (on && a !== null && b !== null && t >= b) this.seek(a)
    }
    this.raf = requestAnimationFrame(this.frame)
  }
}

export const playback = new Playback()
