// App-wide state: the library, settings, which page is showing, and toasts.

import { useSyncExternalStore } from 'react'
import {
  type Backend,
  type Capabilities,
  type ChordLevel,
  type ImportOptions,
  type LyricsMode,
  type SeparationMode,
  type SongSummary,
  deleteSong,
  editSong,
  getCapabilities,
  getSong,
  importPaths,
  importUrl,
  listSongs,
  uploadFile,
} from './api'
import { type EngineInfo, desktop } from './platform'
import { playback } from './playback'

export type View = 'library' | 'profile' | 'player' | 'chords' | 'transpose'
export type SortKey = 'added' | 'title' | 'artist' | 'bpm' | 'key'
export type Filter = 'all' | 'ready' | 'processing' | 'major' | 'minor'

export interface Settings {
  mode: SeparationMode
  backend: Backend
  chordLevel: ChordLevel
  sort: SortKey
  sortDesc: boolean
  sidebar: boolean
  /** How the song's chord chart draws chords. */
  chordView: 'piano' | 'guitar'
  /** Lyrics for new songs: LRCLIB, else transcribed ('auto'); LRCLIB only; or none. */
  lyrics: LyricsMode
}

export interface Toast {
  id: number
  message: string
  error: boolean
}

export interface AppState {
  songs: SongSummary[] | null
  libraryError: string | null
  capabilities: Capabilities | null
  engine: EngineInfo | null
  view: View
  /** The song open in the player (also the one in the mini player). */
  songId: string | null
  settings: Settings
  toast: Toast | null
  /** Bumped to ask the library's search field for focus (⌘F). */
  focusSearch: number
  addOpen: boolean
  /** The chord the Chord Library shows. */
  chord: { root: number; type: string }
}

const SETTINGS_KEY = 'keyfinder.settings'
const DEFAULT_SETTINGS: Settings = {
  mode: '4stems',
  backend: 'auto',
  chordLevel: 'intermediate',
  sort: 'added',
  sortDesc: true,
  sidebar: true,
  lyrics: 'auto',
  chordView: 'piano',
}

function loadSettings(): Settings {
  try {
    return { ...DEFAULT_SETTINGS, ...JSON.parse(localStorage.getItem(SETTINGS_KEY) ?? '{}') }
  } catch {
    return DEFAULT_SETTINGS
  }
}

let state: AppState = {
  songs: null,
  libraryError: null,
  capabilities: null,
  engine: null,
  view: 'library',
  songId: null,
  settings: loadSettings(),
  toast: null,
  focusSearch: 0,
  addOpen: false,
  chord: { root: 0, type: 'maj' },
}
const listeners = new Set<() => void>()

export function getState() {
  return state
}

export function setState(patch: Partial<AppState>) {
  state = { ...state, ...patch }
  listeners.forEach((fn) => fn())
}

export function useApp<T>(select: (s: AppState) => T): T {
  return useSyncExternalStore(
    (fn) => {
      listeners.add(fn)
      return () => listeners.delete(fn)
    },
    () => select(state),
  )
}

export function updateSettings(patch: Partial<Settings>) {
  const settings = { ...state.settings, ...patch }
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings))
  } catch {
    /* private mode */
  }
  setState({ settings })
}

// ------------------------------------------------------------------ toasts

let toastSeq = 0
let toastTimer = 0
export function toast(message: string, error = false) {
  clearTimeout(toastTimer)
  setState({ toast: { id: ++toastSeq, message, error } })
  toastTimer = window.setTimeout(() => setState({ toast: null }), error ? 7000 : 3500)
}

export const errorMessage = (e: unknown) => String((e as Error)?.message ?? e)

// ------------------------------------------------------------------ routing

export function navigate(view: View, songId?: string) {
  const hash =
    view === 'player' && songId
      ? `#/song/${songId}`
      : view === 'profile' || view === 'chords' || view === 'transpose'
        ? `#/${view}`
        : '#/'
  if (location.hash !== hash) location.hash = hash
  else applyRoute()
}

/** Opens the Chord Library at a chord: its root's pitch class and its type ("min7"). */
export function openChord(root: number, type: string) {
  location.hash = `#/chords/${root}/${type}`
}

export function applyRoute() {
  const m = location.hash.match(/^#\/song\/([0-9a-f]{32})$/)
  const chord = location.hash.match(/^#\/chords(?:\/(\d{1,2})\/([\w-]+))?$/)
  if (m) setState({ view: 'player', songId: m[1] })
  else if (chord) setState({ view: 'chords', chord: chord[1] ? { root: Number(chord[1]) % 12, type: chord[2] } : state.chord })
  else setState({ view: location.hash === '#/profile' ? 'profile' : location.hash === '#/transpose' ? 'transpose' : 'library' })
}

// ------------------------------------------------------------------ library

let pollTimer = 0

export async function refreshLibrary() {
  clearTimeout(pollTimer)
  try {
    const songs = await listSongs()
    setState({ songs, libraryError: null })
    // Follow processing songs closely; otherwise check now and then (another window, the CLI).
    const busy = songs.some((s) => s.status === 'queued' || s.status === 'processing')
    pollTimer = window.setTimeout(refreshLibrary, busy ? 1200 : 15000)
  } catch (e) {
    setState({ libraryError: errorMessage(e) })
    pollTimer = window.setTimeout(refreshLibrary, 3000)
  }
}

export async function loadCapabilities() {
  try {
    setState({ capabilities: await getCapabilities() })
  } catch {
    window.setTimeout(loadCapabilities, 2000)
  }
}

function importOptions(): ImportOptions {
  const { mode, backend, lyrics } = state.settings
  const hasDemucs = state.capabilities?.backends.includes('demucs')
  // The fast DSP separator does 2 or 4 stems; ask for 4 when 6 isn't possible.
  if (mode === '6stems' && !hasDemucs) return { mode: '4stems', backend: 'auto', lyrics }
  if (backend === 'demucs' && !hasDemucs) return { mode, backend: 'auto', lyrics }
  return { mode, backend, lyrics }
}

function added(count: number, failed: string[]) {
  if (failed.length) toast(failed.join(' · '), true)
  else if (count) toast(count === 1 ? 'Song added. Finding its key, tempo and chords…' : `${count} songs added.`)
  void refreshLibrary()
}

/** Desktop: files picked in a native dialog, dropped on the window, or opened with the app. */
export async function addPaths(paths: string[]) {
  if (!paths.length) return
  try {
    const { created, failed } = await importPaths(paths, importOptions())
    added(
      created.length,
      failed.map((f) => `${f.path.split(/[\\/]/).pop()}: ${f.error}`),
    )
  } catch (e) {
    toast(errorMessage(e), true)
  }
}

/** Dropped or chosen File objects: by path on the desktop, uploaded in a browser. */
export async function addFiles(files: File[]) {
  if (!files.length) return
  if (desktop) {
    const paths = files.map((f) => desktop!.pathForFile(f)).filter(Boolean)
    if (paths.length) return addPaths(paths)
  }
  let count = 0
  const failed: string[] = []
  for (const file of files) {
    try {
      await uploadFile(file, importOptions())
      count++
    } catch (e) {
      failed.push(`${file.name}: ${errorMessage(e)}`)
    }
    void refreshLibrary()
  }
  added(count, failed)
}

export async function addUrl(url: string) {
  await importUrl(url, importOptions())
  added(1, [])
}

export async function removeSong(id: string) {
  await deleteSong(id)
  if (state.songId === id) setState({ songId: null })
  await refreshLibrary()
}

export async function renameSong(id: string, patch: { title?: string; artist?: string }) {
  await editSong(id, patch)
  await refreshLibrary()
}

// ------------------------------------------------------------------ playback

/** Loads a song into the player (if it isn't already) and optionally starts it. */
export async function loadSong(id: string, { autoplay = false } = {}) {
  if (playback.state.song?.id !== id) {
    const song = await getSong(id)
    if (song.status !== 'ready' || !song.analysis) throw new Error('This song is still being processed.')
    playback.load(song)
  }
  if (autoplay) await playback.play()
}

/** The ready songs in library order (newest first), for the mini player's previous / next. */
export function neighbour(id: string, step: 1 | -1): string | null {
  const ready = (state.songs ?? []).filter((s) => s.status === 'ready').sort((a, b) => b.created_at - a.created_at)
  const i = ready.findIndex((s) => s.id === id)
  if (i < 0 || !ready.length) return ready[0]?.id ?? null
  return ready[(i + step + ready.length) % ready.length].id
}
