/**
 * Updates (the desktop app, as in Player): KeyFinder looks for a newer release on GitHub when it
 * starts and every few hours, puts a dot on Profile when there is one, and installs it when asked.
 * The work is in electron/updates.ts; this keeps what the button and its window show.
 */
import { useSyncExternalStore } from 'react'
import { desktop } from '.'
import type { FoundUpdate, PreviousVersion, UpdatePackage, UpdateResult } from './types'


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
  /** Why update packages can't install here, if they can't. */
  packageBlocker: string | null
  /** A zip package picked and checked, waiting for Install. */
  pkg: UpdatePackage | null
  /** The version kept from before the last update. */
  previous: PreviousVersion | null
  /** How the last update or Go Back went (shown once after the restart). */
  result: UpdateResult | null
  /** Installing a package or going back: KeyFinder is about to restart. */
  restarting: 'package' | 'revert' | null
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
  packageBlocker: null,
  pkg: null,
  previous: null,
  result: null,
  restarting: null,
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

/** Opens a .zip update package and checks it; installing waits for installPackage(). */
export async function pickPackage(): Promise<void> {
  if (!desktop) return
  set({ error: null })
  try {
    const pkg = await desktop.updates.pickPackage()
    if (pkg) set({ pkg })
  } catch (e) {
    set({ pkg: null })
    throw new Error(message(e))
  }
}

export async function discardPackage(): Promise<void> {
  set({ pkg: null })
  await desktop?.updates.discardPackage()
}

/** Installs the package picked; KeyFinder restarts, so this only returns on failure. */
export async function installPackage(): Promise<void> {
  if (!desktop || !state.pkg) return
  set({ restarting: 'package' })
  try {
    await desktop.updates.installPackage()
  } catch (e) {
    set({ restarting: null })
    throw new Error(message(e))
  }
}

/** Puts the previous version back; KeyFinder restarts, so this only returns on failure. */
export async function revertUpdate(): Promise<void> {
  if (!desktop || !state.previous) return
  set({ restarting: 'revert' })
  try {
    await desktop.updates.revert()
  } catch (e) {
    set({ restarting: null })
    throw new Error(message(e))
  }
}

export const dismissResult = () => set({ result: null })

/** Reads the version and whether there's a token, then checks soon after start-up and every few hours. */
export function startUpdateChecks(): () => void {
  if (!desktop) return () => {}
  let alive = true
  void desktop.updates.info().then(({ version, hasToken, blocker, packageBlocker }) => {
    if (alive) set({ version, hasToken, blocker, packageBlocker })
  })
  void desktop.updates.previous().then((previous) => alive && set({ previous }))
  void desktop.updates.takeResult().then((result) => alive && result && set({ result }))
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
