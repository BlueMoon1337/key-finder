// Contract between the renderer and the Electron main process. Types only: imported by both sides.

/** Where a song is being added from (the Add a Song sheet). 'stems': a zip or folder of stems. */
export type ImportSource = 'file' | 'camera' | 'music' | 'stems'

/** Commands from the native menus. */
export type MenuCommand =
  | 'add-song'
  | 'import-file'
  | 'find'
  | 'go-library'
  | 'go-profile'
  | 'toggle-play'
  | 'seek-back'
  | 'seek-forward'
  | 'pitch-up'
  | 'pitch-down'
  | 'speed-up'
  | 'speed-down'
  | 'loop'
  | 'metronome'
  | 'export'
  | 'save-copy'
  | 'check-updates'

export type EngineStatus = 'starting' | 'ready' | 'restarting' | 'failed'

export interface EngineInfo {
  status: EngineStatus
  /** Why it failed, with the end of its log. */
  error: string | null
  version: string | null
  libraryPath: string
}

export interface FoundUpdate {
  version: string
  current: string
  notes: string | null
  date: string | null
}

export interface UpdateInfo {
  version: string
  hasToken: boolean
  /** Why updates can't install here: 'translocated' | 'development'. */
  blocker: string | null
  /** Why update packages can't install here (as blocker; a packaged Linux build can take them). */
  packageBlocker: string | null
}

/** A zip update package, looked at but not yet installed (electron/packages.ts). */
export interface UpdatePackage {
  /** interface: a new app.asar (the engine is kept); app: a whole KeyFinder.app; installer: Windows. */
  kind: 'interface' | 'app' | 'installer'
  version: string
  current: string
  /** Signed with KeyFinder's release key. */
  signed: boolean
  compared: 'newer' | 'same' | 'older'
  notes: string | null
  file: string
  /** Something to know before installing. */
  warning: string | null
}

/** The version kept from before the last update, to go back to. */
export interface PreviousVersion {
  version: string
  kind: 'interface' | 'bundle' | 'dir'
  savedAt: number
}

export interface UpdateResult {
  ok: boolean
  action: 'update' | 'revert'
  version: string
  message: string
}

export interface DesktopAPI {
  platform: string
  /** Base URL of the engine's API (it adds the engine's token on the way). */
  apiBase: string
  engine: {
    info(): Promise<EngineInfo>
    restart(): Promise<void>
    onStatus(cb: (info: EngineInfo) => void): () => void
  }
  /** Native Open dialog for a source; resolves to absolute paths ([] if cancelled). */
  pickFiles(source: ImportSource): Promise<string[]>
  /** The path of a dropped file. */
  pathForFile(file: File): string
  /**
   * Native Save dialog, then saves what the API returns at `apiPath` (an export or a stem) there.
   * Resolves to the saved path, or null if cancelled.
   */
  saveFromApi(apiPath: string, suggestedName: string): Promise<string | null>
  /** A folder dialog, then saves each item there (never over another file). Resolves to the folder, or null. */
  saveManyFromApi(items: { apiPath: string; name: string }[]): Promise<string | null>
  /** Shows the library folder (or one song's folder) in Finder / Explorer. */
  reveal(songId?: string): Promise<void>
  /** Files opened with the app (Open With, the Dock icon, the command line). */
  onOpenFiles(cb: (paths: string[]) => void): () => void
  onMenu(cb: (cmd: MenuCommand) => void): () => void
  /** Saving a copy of the app itself (a .dmg or .zip) to give to someone or move to another computer. */
  copy: {
    info(): Promise<{ formats: ('dmg' | 'zip')[]; blocker: string | null; arch: string }>
    /** A Save dialog, then the copy; resolves to the saved path, or null if cancelled. */
    save(format: 'dmg' | 'zip'): Promise<string | null>
  }
  updates: {
    info(): Promise<UpdateInfo>
    setToken(token: string): Promise<void>
    check(): Promise<FoundUpdate | null>
    install(): Promise<void>
    onProgress(cb: (p: { received: number; total: number | null }) => void): () => void
    /** An Open dialog for a .zip package, then what it is (null if cancelled). Nothing is installed yet. */
    pickPackage(): Promise<UpdatePackage | null>
    discardPackage(): Promise<void>
    /** Installs the package picked last; KeyFinder restarts. */
    installPackage(): Promise<void>
    previous(): Promise<PreviousVersion | null>
    /** Puts the previous version back; KeyFinder restarts. */
    revert(): Promise<void>
    /** How the last update or Go Back went, once, after the restart. */
    takeResult(): Promise<UpdateResult | null>
  }
}
