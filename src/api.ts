// The engine's HTTP API (keyfinder/server.py), the same in the desktop app and a browser.

import { API_BASE, desktop } from './platform'

export type SongStatus = 'queued' | 'processing' | 'ready' | 'error'
export type SeparationMode = '2stems' | '4stems' | '6stems' | 'none'
export type Backend = 'auto' | 'demucs' | 'dsp'
export type ChordLevel = 'basic' | 'intermediate' | 'advanced'

export interface SongSummary {
  id: string
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
  mode: SeparationMode
  backend: string | null
  stems: string[]
  key?: string
  camelot?: string
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

export interface Analysis {
  duration: number
  tuning_cents: number
  key: Key
  bpm: number
  beats: number[]
  downbeats: number[]
  beats_per_bar: number
  chords: Record<ChordLevel, Chord[]>
  waveform: number[]
}

export interface Song extends SongSummary {
  analysis: Analysis | null
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

export interface Capabilities {
  version: string
  backends: string[]
  modes: Record<string, string[]>
  dsp_modes: string[]
  rubberband: boolean
  max_upload_mb: number
  desktop: boolean
  demucs: DemucsStatus
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
export const downloadDemucs = (model: string) => request<DemucsStatus>('/api/demucs/download', json('POST', { model }))
export const listSongs = () => request<SongSummary[]>('/api/songs')
export const getSong = (id: string) => request<Song>(`/api/songs/${id}`)
export const deleteSong = (id: string) => request<null>(`/api/songs/${id}`, { method: 'DELETE' })
export const editSong = (id: string, patch: { title?: string; artist?: string }) =>
  request<SongSummary>(`/api/songs/${id}`, json('PATCH', patch))

export interface ImportOptions {
  mode: SeparationMode
  backend: Backend
}

/** Browser: upload a file. */
export function uploadFile(file: File, opts: ImportOptions) {
  const form = new FormData()
  form.append('file', file)
  form.append('mode', opts.mode)
  form.append('backend', opts.backend)
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
  format: 'mp3' | 'wav' | 'm4a'
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
