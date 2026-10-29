import type { DesktopAPI } from './types'

/** The Electron bridge from the preload script, or null when running as a web page. */
export const desktop: DesktopAPI | null =
  (window as unknown as { keyfinderDesktop?: DesktopAPI }).keyfinderDesktop ?? null

/** Where the engine's API lives: app://keyfinder in the desktop app, this origin in a browser. */
export const API_BASE = desktop?.apiBase ?? ''

export const isMac = (desktop?.platform ?? navigator.platform).toLowerCase().startsWith('mac') || desktop?.platform === 'darwin'

export type { DesktopAPI, EngineInfo, FoundUpdate, ImportSource, MenuCommand } from './types'
