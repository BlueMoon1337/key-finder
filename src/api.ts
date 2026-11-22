// The engine's HTTP API (keyfinder/server.py), the same in the desktop app and a browser.

import { API_BASE, desktop } from './platform'

export type SongStatus = 'queued' | 'processing' | 'ready' | 'error'
export type SeparationMode = '2stems' | '4stems' | '6stems' | 'none'
export type Backend = 'auto' | 'best' | 'demucs' | 'dsp'
export type ChordLevel = 'basic' | 'intermediate' | 'advanced'

export interface SongSummary {
  id: string
  /** Separated with the vocals split into lead and choir, and with strings & pads taken out. */
  choir?: boolean
  strings?: boolean
  title: string
  artist: string
  cover: boolean
  status: SongStatus
  progress: number
  stage: string
  error: string | null
  /** Something to know about how it was processed (e.g. Demucs couldn't be downloaded). */
  warning: string | null
  created_at: number
  /** 'stems': it arrived as stems (a zip, a folder, a Player song) and wasn't separated. */
  mode: SeparationMode | 'stems'
  backend: string | null
  stems: string[]
  key?: string
  camelot?: string
  /** Every key in order, when the song changes key. */
  keys?: string[]
  /** Every tempo in order, when the song changes tempo. */
  tempos?: number[]
  /** Every chord the song uses, at any detail level, as "root:quality" ("7:maj" is G). */
  chords?: string[]
  /** Songs added before lyrics existed have none. */
  lyrics_status?: LyricsStatus
  bpm?: number
  duration?: number
}

export interface Key {
  tonic: number
  mode: 'major' | 'minor'
  name: string
  camelot: string
  relative: string
  flats: boolean
  confidence: number
}

export interface Chord {
  start: number
  end: number
  root: number | null
  quality: string | null
  /** A chord tone other than the root in the bass (an inversion, written G/B); null otherwise. */
  bass?: number | null
  label: string
}

/** A stretch of a song in one key (a medley or a key change has several). */
export interface KeySection {
  start: number
  end: number
  tonic: number
  mode: 'major' | 'minor'
  name: string
  camelot: string
  flats: boolean
}

export interface TempoSection {
  start: number
  end: number
  bpm: number
}

export interface Analysis {
  duration: number
  tuning_cents: number
  key: Key
  /** The song's keys in order; one covering the whole song when it doesn't change key. */
  key_sections?: KeySection[]
  bpm: number
  beats: number[]
  downbeats: number[]
  beats_per_bar: number
  /** The song's tempos in order; one covering the whole song when it keeps one tempo. */
  tempo_sections?: TempoSection[]
  chords: Record<ChordLevel, Chord[]>
  waveform: number[]
  /** For a song that arrived as stems: where the beats, key and tempo came from. */
  sources?: { beats: 'click' | 'audio'; key: 'name' | 'audio'; bpm: 'name' | 'audio' }
  /** Bar 1, the tempo changes and the bar lengths (beats per bar), from the beats; sent with the song. */
  beat_map?: BeatMap
}

export interface BeatMap {
  offset: number
  tempos: { start: number; bpm: number }[]
  meters: { start: number; beats: number }[]
}

/** What a stem is, by Player's buses (plus the reference mix). */
export type StemKind =
  | 'click' | 'guide' | 'reference' | 'drums' | 'percussion' | 'loops' | 'bass' | 'piano' | 'keys'
  | 'eg' | 'ag' | 'strings' | 'horns' | 'vocals' | 'fx' | 'aux'

export interface LyricWord {
  start: number
  end: number
  text: string
}

export interface LyricLine {
  start: number
  end: number
  words: LyricWord[]
}

export interface Lyrics {
  /** Where the words came from; 'edited' once corrected by hand. */
  source: 'lrclib' | 'whisper' | 'edited'
  language: string | null
  lines: LyricLine[]
  lrclib?: { id: number; track: string; artist: string } | null
  edited_from?: 'lrclib' | 'whisper'
}

export type LyricsMode = 'auto' | 'online' | 'off'
export type LyricsStatus = 'waiting' | 'queued' | 'working' | 'ready' | 'none' | 'failed' | 'off'

export interface Song extends SongSummary {
  analysis: Analysis | null
  lyrics?: Lyrics | null
  lyrics_mode?: LyricsMode
  lyrics_stage?: string | null
  lyrics_note?: string | null
  lyrics_progress?: number
  /** Each stem's name ("EG 1", "Click Track") and kind, by id. */
  stem_names: Record<string, string>
  stem_kinds: Record<string, StemKind>
}

export interface DemucsStatus {
  installed: boolean
  /** Where it runs: cuda, mps (Apple silicon) or cpu. */
  device?: string
  /** Whether each model's weights are on this computer. */
  models?: Record<string, boolean>
  downloading?: string | null
  download_error?: string | null
}

/** Best quality separation's vocal model (BS-RoFormer, keyfinder/roformer.py). */
export interface BestStatus {
  installed: boolean
  downloaded?: boolean
  downloading?: boolean
  /** 0..1 while downloading. */
  progress?: number | null
  download_error?: string | null
  /** Bytes. */
  size?: number
}

export interface LyricsModelStatus {
  installed: boolean
  model?: string
  size_mb?: number
  downloaded?: boolean
  downloading?: boolean
  download_error?: string | null
}

export interface Capabilities {
  version: string
  backends: string[]
  modes: Record<string, string[]>
  dsp_modes: string[]
  rubberband: boolean
  max_upload_mb: number
  desktop: boolean
  demucs: DemucsStatus
  best?: BestStatus
  lyrics?: LyricsModelStatus
  /** Choir isolation's model (vocal_split.py); absent from older engines. */
  choir?: ChoirModelStatus
}

export interface ChoirModelStatus {
  /** Whether this engine can run it (onnxruntime and PyTorch). */
  installed: boolean
  model: string
  downloaded: boolean
  downloading: boolean
  /** 0..1 while downloading. */
  progress: number | null
  download_error: string | null
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
  }
}

export const apiUrl = (path: string) => `${API_BASE}${path}`

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(apiUrl(path), init)
  } catch {
    throw new ApiError('The KeyFinder engine isn’t answering.', 0)
  }
  if (!res.ok) {
    let detail = res.statusText || `Error ${res.status}`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join('; ')
    } catch {
      /* not JSON */
    }
    throw new ApiError(detail.charAt(0).toUpperCase() + detail.slice(1), res.status)
  }
  return (res.status === 204 ? null : await res.json()) as T
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const getCapabilities = () => request<Capabilities>('/api/capabilities')
export const downloadLyricsModel = () => request<LyricsModelStatus>('/api/lyrics/download', { method: 'POST' })
export const findLyrics = (id: string, mode?: 'auto' | 'online') =>
  request<SongSummary>(`/api/songs/${id}/lyrics`, json('POST', { mode: mode ?? null }))
export const editLyrics = (id: string, lines: string[]) => request<Lyrics>(`/api/songs/${id}/lyrics`, json('PUT', { lines }))
export const downloadDemucs = (model: string) => request<DemucsStatus>('/api/demucs/download', json('POST', { model }))
export const downloadChoirModel = () => request<ChoirModelStatus>('/api/choir/download', { method: 'POST' })
export const downloadBest = () => request<BestStatus>('/api/best/download', json('POST', {}))
export const listSongs = () => request<SongSummary[]>('/api/songs')
export const getSong = (id: string) => request<Song>(`/api/songs/${id}`)
export const deleteSong = (id: string) => request<null>(`/api/songs/${id}`, { method: 'DELETE' })
export const editSong = (id: string, patch: { title?: string; artist?: string; tempo?: 'double' | 'half' }) =>
  request<SongSummary>(`/api/songs/${id}`, json('PATCH', patch))

export interface ImportOptions {
  mode: SeparationMode
  backend: Backend
  lyrics: LyricsMode
  /** Split the vocals into lead and choir (needs Demucs). */
  choir?: boolean
  /** Take strings & pads out of the other instruments (needs Demucs). */
  strings?: boolean
}

/** Browser: upload a file. */
export function uploadFile(file: File, opts: ImportOptions) {
  const form = new FormData()
  form.append('file', file)
  form.append('mode', opts.mode)
  form.append('backend', opts.backend)
  form.append('lyrics', opts.lyrics)
  form.append('choir', String(!!opts.choir))
  form.append('strings', String(!!opts.strings))
  return request<SongSummary>('/api/songs', { method: 'POST', body: form })
}

/** Desktop: import files straight from disk. */
export const importPaths = (paths: string[], opts: ImportOptions) =>
  request<{ created: SongSummary[]; failed: { path: string; error: string }[] }>(
    '/api/songs/local',
    json('POST', { paths, ...opts }),
  )

export const importUrl = (url: string, opts: ImportOptions) => request<SongSummary>('/api/songs/url', json('POST', { url, ...opts }))

export const stemPath = (id: string, stem: string, semitones = 0) =>
  `/api/songs/${id}/stems/${encodeURIComponent(stem)}${semitones ? `?semitones=${semitones}` : ''}`

export const coverUrl = (song: Pick<SongSummary, 'id' | 'cover'>) => (song.cover ? apiUrl(`/api/songs/${song.id}/cover`) : null)

export interface ExportOptions {
  semitones: number
  speed: number
  volumes: Record<string, number>
  /** 'player': every stem as a WAV, with a click on the song's beats, zipped for Player. */
  format: 'mp3' | 'wav' | 'm4a' | 'player'
}

export function exportPath(id: string, o: ExportOptions) {
  const q = new URLSearchParams({
    semitones: String(o.semitones),
    speed: String(o.speed),
    format: o.format,
    volumes: Object.entries(o.volumes)
      .map(([k, v]) => `${k}:${v.toFixed(3)}`)
      .join(','),
  })
  return `/api/songs/${id}/export?${q}`
}

/** The Player package's file name. Player reads the key and tempo from it, so it must be kept. */
export const playerPackageName = (id: string, semitones: number, speed: number) =>
  request<{ name: string }>(`/api/songs/${id}/export/player-name?${new URLSearchParams({ semitones: String(semitones), speed: String(speed) })}`).then(
    (r) => r.name,
  )

// ------------------------------------------------------------------ transposing files

/** A file being transposed: what KeyFinder found in it. */
export interface TransposeItem {
  id: string
  name: string
  format: string
  title: string
  artist: string
  duration: number
  key: { name: string; tonic: number; mode: 'major' | 'minor'; camelot?: string; confidence?: number }
  /** Every key in order, when it changes key. */
  keys: string[] | null
  bpm: number
  tuning_cents: number
}

export const TRANSPOSE_FORMATS = ['mp3', 'wav', 'm4a', 'flac'] as const
export type TransposeFormat = (typeof TRANSPOSE_FORMATS)[number]

export function addTransposeFile(file: File) {
  const form = new FormData()
  form.append('file', file)
  return request<TransposeItem>('/api/transpose', { method: 'POST', body: form })
}
export const addTransposePaths = (paths: string[]) =>
  request<{ created: TransposeItem[]; failed: { path: string; error: string }[] }>('/api/transpose/local', json('POST', { paths }))
export const transposePath = (id: string, semitones: number, speed: number, format: TransposeFormat) =>
  `/api/transpose/${id}/render?${new URLSearchParams({ semitones: String(semitones), speed: String(speed), format })}`
export const deleteTranspose = (id: string) => request<null>(`/api/transpose/${id}`, { method: 'DELETE' })

/** Saves several things the API makes into one folder (desktop), or downloads each (browser). */
export async function saveManyFromApi(items: { apiPath: string; name: string }[]): Promise<string | null> {
  if (desktop) return desktop.saveManyFromApi(items)
  for (const it of items) await saveFromApi(it.apiPath, it.name)
  return items.length ? 'Downloads' : null
}

/** Saves something the API makes: a Save dialog on the desktop, a download in a browser. */
export async function saveFromApi(path: string, suggestedName: string): Promise<string | null> {
  if (desktop) return desktop.saveFromApi(path, suggestedName)
  const a = document.createElement('a')
  a.href = apiUrl(path)
  a.download = suggestedName
  document.body.append(a)
  a.click()
  a.remove()
  return suggestedName
}
