/**
 * Updates (the desktop app, as in Player): KeyFinder looks for a newer release on GitHub when it
 * starts and every few hours, puts a dot on Profile when there is one, and installs it when asked.
 * The work is in electron/updates.ts; this keeps what the button and its window show.
 */
import { useSyncExternalStore } from 'react'
import { desktop } from '.'
import type { FoundUpdate } from './types'


/** Where releases come from (electron/updates.ts reads the same repository). */
export const REPOSITORY_NAME = 'BlueMoon1337/key-finder'

export type UpdateStatus = 'idle' | 'checking' | 'none' | 'available' | 'installing' | 'error'

export interface UpdateState {
  status: UpdateStatus
  version: string | null
  hasToken: boolean | null
  found: FoundUpdate | null
  error: string | null
  /** While installing: bytes received, and the total if known. */
  progress: { received: number; total: number | null } | null
  checkedAt: number | null
  /** Why updates can't install here ('translocated', 'development'), if they can't. */
  blocker: string | null
}

let state: UpdateState = {
  status: 'idle',
  version: null,
  hasToken: null,
  found: null,
  error: null,
  progress: null,
  checkedAt: null,
  blocker: null,
}
const listeners = new Set<() => void>()

function set(patch: Partial<UpdateState>) {
  state = { ...state, ...patch }
  listeners.forEach((fn) => fn())
}

export function useUpdates(): UpdateState {
  return useSyncExternalStore(
    (fn) => {
      listeners.add(fn)
      return () => listeners.delete(fn)
    },
    () => state,
  )
}

/** Errors from the main process arrive wrapped ("Error invoking remote method …"); keep the message. */
function message(e: unknown): string {
  return String((e as Error)?.message ?? e).replace(/^Error invoking remote method '[^']+': (Error: )?/, '')
}

const CHECK_EVERY_MS = 6 * 60 * 60 * 1000

/** Looks for an update. A quiet check (the automatic ones) keeps a failure to itself. */
export async function checkForUpdates({ quiet = false } = {}): Promise<void> {
  const before = state
  if (!desktop || before.status === 'checking' || before.status === 'installing' || !before.hasToken) return
  set({ status: 'checking', error: null })
  try {
    const found = await desktop.updates.check()
    set({ status: found ? 'available' : 'none', found, checkedAt: Date.now() })
  } catch (e) {
    // A quiet check that fails leaves things as they were (no network at the venue, say).
    if (quiet) set({ status: before.found ? 'available' : 'idle' })
    else set({ status: 'error', error: message(e) })
  }
}

export async function saveToken(token: string): Promise<void> {
  if (!desktop) return
  try {
    await desktop.updates.setToken(token)
  } catch (e) {
    throw new Error(message(e))
  }
  const { hasToken } = await desktop.updates.info()
  set({ hasToken, found: null, status: 'idle', error: null })
  if (hasToken) await checkForUpdates()
}

export async function installUpdate(): Promise<void> {
  if (!desktop || state.status !== 'available') return
  set({ status: 'installing', progress: { received: 0, total: null }, error: null })
  const stop = desktop.updates.onProgress((progress) => set({ progress }))
  try {
    // KeyFinder restarts when it's done, so this only returns on failure.
    await desktop.updates.install()
  } catch (e) {
    set({ status: 'error', error: message(e), progress: null, found: null })
  } finally {
    stop()
  }
}

/** Reads the version and whether there's a token, then checks soon after start-up and every few hours. */
export function startUpdateChecks(): () => void {
  if (!desktop) return () => {}
  let alive = true
  void desktop.updates.info().then(({ version, hasToken, blocker }) => {
    if (alive) set({ version, hasToken, blocker })
  })
  const first = window.setTimeout(() => void checkForUpdates({ quiet: true }), 15_000)
  const every = window.setInterval(() => void checkForUpdates({ quiet: true }), CHECK_EVERY_MS)
  return () => {
    alive = false
    window.clearTimeout(first)
    window.clearInterval(every)
  }
}

/** "12.3 MB of 40.1 MB" */
export function progressText(p: { received: number; total: number | null }): string {
  const mb = (n: number) => `${(n / 1_000_000).toFixed(1)} MB`
  return p.total ? `${mb(p.received)} of ${mb(p.total)}` : mb(p.received)
}
