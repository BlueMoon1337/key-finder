// KeyFinder's main process. The window, menus, IPC trust check, window-state memory and
// single-instance lock follow Player (BlueMoon1337/Player, electron/main.ts); the audio work is
// done by the Python engine (engine.ts), reached through the app:// protocol.

import {
  BrowserWindow,
  Menu,
  type MenuItemConstructorOptions,
  type Rectangle,
  app,
  dialog,
  ipcMain,
  net,
  protocol,
  screen,
  session,
  shell,
} from 'electron'
import fs from 'node:fs'
import fsp from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { Readable } from 'node:stream'
import { pipeline } from 'node:stream/promises'
import { pathToFileURL } from 'node:url'
import type { ImportSource, MenuCommand } from '../src/platform/types'
import { Engine } from './engine'
import * as share from './share'
import * as packages from './packages'
import * as updates from './updates'

const DEV_URL = process.env.VITE_DEV_SERVER_URL
const RENDERER_DIR = path.join(__dirname, '..', 'dist')
const APP_ORIGIN = 'app://keyfinder'

const AUDIO_EXTENSIONS = ['mp3', 'wav', 'flac', 'm4a', 'aac', 'aif', 'aiff', 'ogg', 'oga', 'opus', 'wma', 'alac', 'caf']
const VIDEO_EXTENSIONS = ['mp4', 'mov', 'm4v', 'webm', 'mkv', 'avi', '3gp']

const MIME: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.json': 'application/json',
  '.woff2': 'font/woff2',
}

const CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "media-src 'self' blob:",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'none'",
].join('; ')

protocol.registerSchemesAsPrivileged([
  { scheme: 'app', privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true, stream: true } },
])

let win: BrowserWindow | null = null
let engine: Engine
/** Files opened with the app before its window was ready. */
let openedFiles: string[] = []

function libraryRoot() {
  return process.env.KEYFINDER_LIBRARY_DIR || path.join(app.getPath('documents'), 'KeyFinder Library')
}

// ------------------------------------------------------------------ protocol

/** Headers the renderer may pass to the engine. */
const FORWARD_HEADERS = ['range', 'content-type', 'accept', 'if-none-match', 'if-modified-since', 'if-range']

/**
 * app://keyfinder/api/... goes to the engine with its token; everything else is the built UI.
 * Keeping both on one origin lets the UI use plain fetch() and <audio> with the Web Audio API.
 */
function registerAppProtocol() {
  protocol.handle('app', async (req) => {
    const url = new URL(req.url)
    if (url.host !== 'keyfinder') return new Response('Not found', { status: 404 })
    const cors: Record<string, string> = DEV_URL
      ? { 'Access-Control-Allow-Origin': new URL(DEV_URL).origin, 'Access-Control-Expose-Headers': 'Content-Disposition, Content-Range' }
      : {}
    if (url.pathname.startsWith('/api/')) {
      if (req.method === 'OPTIONS') {
        return new Response(null, {
          status: 204,
          headers: { ...cors, 'Access-Control-Allow-Methods': 'GET, POST, PATCH, DELETE', 'Access-Control-Allow-Headers': 'Content-Type, Range' },
        })
      }
      return proxyToEngine(req, url, cors)
    }
    return serveRenderer(url)
  })
}

async function proxyToEngine(req: Request, url: URL, cors: Record<string, string>) {
  let port: number
  try {
    port = await engine.ready()
  } catch (e) {
    return Response.json({ detail: (e as Error).message }, { status: 503, headers: cors })
  }
  const headers: Record<string, string> = { 'X-KeyFinder-Token': engine.token }
  for (const name of FORWARD_HEADERS) {
    const v = req.headers.get(name)
    if (v) headers[name] = v
  }
  const hasBody = req.method !== 'GET' && req.method !== 'HEAD'
  try {
    // Node's fetch, not Chromium's: a system proxy must never see the engine's token.
    const res = await fetch(`http://127.0.0.1:${port}${url.pathname}${url.search}`, {
      method: req.method,
      headers,
      body: hasBody ? await req.arrayBuffer() : undefined,
    })
    const out = new Headers(cors)
    res.headers.forEach((v, k) => {
      if (!['content-encoding', 'transfer-encoding', 'connection'].includes(k)) out.set(k, v)
    })
    return new Response(res.body, { status: res.status, headers: out })
  } catch (e) {
    return Response.json({ detail: `The engine didn’t answer: ${(e as Error).message}` }, { status: 502, headers: cors })
  }
}

async function serveRenderer(url: URL) {
  const parts = url.pathname.split('/').filter(Boolean).map(decodeURIComponent)
  let file = path.resolve(RENDERER_DIR, '.' + path.posix.normalize('/' + parts.join('/')))
  if (file !== RENDERER_DIR && !file.startsWith(RENDERER_DIR + path.sep)) return new Response('Forbidden', { status: 403 })
  // Single-page app: anything that isn't a file gets index.html.
  if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) file = path.join(RENDERER_DIR, 'index.html')
  const headers: Record<string, string> = { 'Content-Type': MIME[path.extname(file).toLowerCase()] ?? 'application/octet-stream' }
  if (file.endsWith('.html')) headers['Content-Security-Policy'] = CSP
  try {
    const res = await net.fetch(pathToFileURL(file).toString())
    if (!res.ok) return new Response('Not found', { status: 404 })
    return new Response(res.body, { status: 200, headers })
  } catch {
    return new Response('Not found', { status: 404 })
  }
}

// ------------------------------------------------------------------- window

interface WindowState {
  bounds?: Rectangle
  maximized?: boolean
}

const windowStateFile = () => path.join(app.getPath('userData'), 'window-state.json')

function loadWindowState(): WindowState {
  try {
    const s: WindowState = JSON.parse(fs.readFileSync(windowStateFile(), 'utf8'))
    // Ignore saved bounds that are no longer on any screen (e.g. an unplugged monitor).
    const b = s.bounds
    const visible =
      b &&
      screen.getAllDisplays().some(({ workArea: w }) => b.x < w.x + w.width && b.x + b.width > w.x && b.y < w.y + w.height && b.y + b.height > w.y)
    return visible ? s : { maximized: s.maximized }
  } catch {
    return {}
  }
}

function saveWindowState() {
  if (!win) return
  try {
    fs.writeFileSync(windowStateFile(), JSON.stringify({ bounds: win.getNormalBounds(), maximized: win.isMaximized() }))
  } catch {
    /* non-fatal */
  }
}

function createWindow() {
  const state = loadWindowState()
  win = new BrowserWindow({
    width: 1280,
    height: 820,
    ...state.bounds,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: '#000000',
    title: 'KeyFinder',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      // Keep the playhead, metronome and chord display running when the window is behind others.
      backgroundThrottling: false,
      spellcheck: false,
    },
  })
  if (state.maximized) win.maximize()
  win.once('ready-to-show', () => win?.show())
  void win.loadURL(DEV_URL ?? `${APP_ORIGIN}/index.html`)

  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//.test(url)) void shell.openExternal(url)
    return { action: 'deny' }
  })
  win.webContents.on('will-navigate', (e, url) => {
    // A file dropped outside the drop handling would otherwise replace the app with it.
    if (!url.startsWith(DEV_URL ?? APP_ORIGIN)) e.preventDefault()
  })
  win.webContents.on('did-finish-load', () => flushOpenedFiles())
  win.on('close', saveWindowState)
  win.on('closed', () => {
    win = null
  })
}

function send(cmd: MenuCommand) {
  win?.webContents.send('menu', cmd)
}

// --------------------------------------------------------------------- menu

function buildMenu() {
  const isMac = process.platform === 'darwin'
  const sep = { type: 'separator' } as const
  const checkUpdates: MenuItemConstructorOptions = { label: 'Check for Updates…', click: () => send('check-updates') }
  const settings: MenuItemConstructorOptions = { label: 'Settings…', accelerator: 'CmdOrCtrl+,', click: () => send('go-profile') }
  // Single-key shortcuts (Space, arrows, [ ], L, M) are handled by the renderer so they never
  // fire while typing in a text field; the menu just names them.
  const template: MenuItemConstructorOptions[] = [
    ...(isMac
      ? [
          {
            label: app.name,
            submenu: [
              { role: 'about' },
              checkUpdates,
              sep,
              settings,
              sep,
              { role: 'services' },
              sep,
              { role: 'hide' },
              { role: 'hideOthers' },
              { role: 'unhide' },
              sep,
              { role: 'quit' },
            ] as MenuItemConstructorOptions[],
          },
        ]
      : []),
    {
      label: 'File',
      submenu: [
        { label: 'Add a Song…', accelerator: 'CmdOrCtrl+N', click: () => send('add-song') },
        { label: 'Import File…', accelerator: 'CmdOrCtrl+O', click: () => send('import-file') },
        sep,
        { label: 'Export Mix…', accelerator: 'CmdOrCtrl+E', click: () => send('export') },
        sep,
        { label: 'Show Library Folder', click: () => void shell.openPath(libraryRoot()) },
        ...(share.copyFormats().length ? [sep, { label: 'Save a Copy of KeyFinder…', click: () => send('save-copy') }] : []),
        ...(isMac ? [] : [sep, settings, sep, { role: 'quit' } as MenuItemConstructorOptions]),
      ],
    },
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        sep,
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
        { role: 'selectAll' },
        sep,
        { label: 'Find in Library', accelerator: 'CmdOrCtrl+F', click: () => send('find') },
      ],
    },
    {
      label: 'Playback',
      submenu: [
        { label: 'Play / Pause (Space)', click: () => send('toggle-play') },
        { label: 'Back 5 Seconds (←)', click: () => send('seek-back') },
        { label: 'Forward 5 Seconds (→)', click: () => send('seek-forward') },
        sep,
        { label: 'Pitch Up ( ] )', click: () => send('pitch-up') },
        { label: 'Pitch Down ( [ )', click: () => send('pitch-down') },
        { label: 'Faster', accelerator: 'CmdOrCtrl+Up', click: () => send('speed-up') },
        { label: 'Slower', accelerator: 'CmdOrCtrl+Down', click: () => send('speed-down') },
        sep,
        { label: 'Loop (L)', click: () => send('loop') },
        { label: 'Metronome (M)', click: () => send('metronome') },
      ],
    },
    {
      label: 'View',
      submenu: [
        { label: 'Library', accelerator: 'CmdOrCtrl+1', click: () => send('go-library') },
        { label: 'Profile', accelerator: 'CmdOrCtrl+2', click: () => send('go-profile') },
        sep,
        { role: 'togglefullscreen' },
        ...(app.isPackaged ? [] : ([sep, { role: 'reload' }, { role: 'toggleDevTools' }] as MenuItemConstructorOptions[])),
      ],
    },
    { role: 'windowMenu' },
    ...(isMac ? [] : [{ label: 'Help', submenu: [checkUpdates] }]),
  ]
  Menu.setApplicationMenu(Menu.buildFromTemplate(template))
}

// ---------------------------------------------------------------------- ipc

/** Only our own UI may call into the main process. */
function trusted(e: Electron.IpcMainInvokeEvent) {
  const url = e.senderFrame?.url ?? ''
  return url.startsWith(APP_ORIGIN + '/') || (!!DEV_URL && url.startsWith(DEV_URL))
}

function handle(channel: string, fn: (...args: any[]) => unknown) {
  ipcMain.handle(channel, (e, ...args) => {
    if (!trusted(e)) throw new Error('Untrusted sender')
    return fn(...args)
  })
}

/** Where each Add a Song source opens, and what it lists. */
function pickOptions(source: ImportSource): Electron.OpenDialogOptions {
  const home = os.homedir()
  const existing = (...dirs: string[]) => dirs.find((d) => fs.existsSync(d)) ?? home
  const media = [...AUDIO_EXTENSIONS, ...VIDEO_EXTENSIONS]
  if (source === 'camera') {
    return {
      title: 'Camera Roll',
      defaultPath: existing(
        // Photos exports and phone imports land in Pictures; screen and phone videos often in Movies / Videos.
        app.getPath('pictures'),
        path.join(home, 'Movies'),
        app.getPath('videos'),
      ),
      filters: [
        { name: 'Videos', extensions: VIDEO_EXTENSIONS },
        { name: 'All Media', extensions: media },
      ],
    }
  }
  if (source === 'stems') {
    // MultiTracks downloads, folders of stems and Player's song folders (Documents/Player Library/Songs).
    const player = path.join(app.getPath('documents'), 'Player Library', 'Songs')
    return {
      title: 'Stems',
      defaultPath: existing(player, app.getPath('downloads'), home),
      filters: [{ name: 'Stem zips', extensions: ['zip'] }],
    }
  }
  if (source === 'music') {
    return {
      title: 'Music',
      // The Music app keeps imported (DRM-free) files in Music/Music/Media; iTunes in Music/iTunes.
      defaultPath: existing(
        path.join(app.getPath('music'), 'Music', 'Media.localized', 'Music'),
        path.join(app.getPath('music'), 'Music', 'Media', 'Music'),
        path.join(app.getPath('music'), 'iTunes', 'iTunes Media', 'Music'),
        app.getPath('music'),
      ),
      filters: [{ name: 'Songs', extensions: AUDIO_EXTENSIONS }],
    }
  }
  return {
    title: 'Import File',
    defaultPath: existing(app.getPath('downloads'), home),
    filters: [
      { name: 'Audio, Video and Stem Zips', extensions: [...media, 'zip'] },
      { name: 'All Files', extensions: ['*'] },
    ],
  }
}

/** `/api/songs/<id>/export?…` or `/api/songs/<id>/stems/<stem>?…`: the only things saveFromApi saves. */
/** What saveFromApi may save: a song's export or stem, or a transposed file. */
const SAVABLE = /^\/api\/(songs\/[0-9a-f]{32}\/(export|stems\/[a-z0-9_-]+)|transpose\/[0-9a-f]{32}\/render)(\?[^#]*)?$/

const cleanName = (name: unknown, fallback: string) =>
  typeof name === 'string' && name.trim() ? name.replace(/[\\/:*?"<>|]+/g, ' ').slice(0, 180) : fallback

/** Fetches what the engine makes at ``apiPath`` into ``filePath`` (via a .partial file). */
async function download(apiPath: string, filePath: string) {
  const port = await engine.ready()
  const res = await fetch(`http://127.0.0.1:${port}${apiPath}`, { headers: { 'X-KeyFinder-Token': engine.token } })
  if (!res.ok || !res.body) {
    let detail = `${res.status}`
    try {
      detail = ((await res.json()) as { detail?: string }).detail ?? detail
    } catch {
      /* not JSON */
    }
    throw new Error(`Couldn’t export: ${detail}`)
  }
  const partial = `${filePath}.partial`
  try {
    await pipeline(Readable.fromWeb(res.body as never), fs.createWriteStream(partial))
    await fsp.rename(partial, filePath)
  } catch (e) {
    await fsp.rm(partial, { force: true })
    throw e
  }
}

function registerIpc() {
  handle('engine:info', () => engine.info())
  handle('app:copy-info', () => ({ formats: share.copyFormats(), blocker: share.copyBlocker(), arch: process.arch }))
  handle('app:save-copy', (format: unknown) => share.saveCopy(win, format === 'dmg' ? 'dmg' : 'zip'))
  handle('engine:restart', () => engine.restart())

  handle('dialog:pick', async (source: unknown) => {
    const kind: ImportSource = source === 'camera' || source === 'music' || source === 'stems' ? source : 'file'
    // Stems are zips or folders. A Mac's dialog can offer both; elsewhere it's folders (zips come in through Import File).
    const stems: Electron.OpenDialogOptions['properties'] =
      process.platform === 'darwin' ? ['openFile', 'openDirectory', 'multiSelections'] : ['openDirectory', 'multiSelections']
    const properties = kind === 'stems' ? stems : (['openFile', 'multiSelections'] as Electron.OpenDialogOptions['properties'])
    const opts: Electron.OpenDialogOptions = { buttonLabel: 'Add', properties, ...pickOptions(kind) }
    const r = win ? await dialog.showOpenDialog(win, opts) : await dialog.showOpenDialog(opts)
    return r.canceled ? [] : r.filePaths
  })

  handle('file:save-from-api', async (apiPath: unknown, suggestedName: unknown) => {
    if (typeof apiPath !== 'string' || !SAVABLE.test(apiPath)) throw new Error('Not something that can be saved')
    const name = cleanName(suggestedName, 'KeyFinder export.mp3')
    const ext = path.extname(name).slice(1).toLowerCase() || 'mp3'
    const opts: Electron.SaveDialogOptions = {
      title: 'Save',
      defaultPath: path.join(app.getPath('music'), name),
      filters: [{ name: ext.toUpperCase(), extensions: [ext] }],
    }
    const r = win ? await dialog.showSaveDialog(win, opts) : await dialog.showSaveDialog(opts)
    if (r.canceled || !r.filePath) return null
    await download(apiPath, r.filePath)
    shell.showItemInFolder(r.filePath)
    return r.filePath
  })

  // Several files into one folder, chosen once: transposing a batch.
  handle('file:save-many-from-api', async (items: unknown) => {
    if (!Array.isArray(items) || !items.length) return null
    const list = items.map((it) => ({ apiPath: String(it?.apiPath ?? ''), name: cleanName(it?.name, 'KeyFinder export.mp3') }))
    if (list.some((it) => !SAVABLE.test(it.apiPath))) throw new Error('Not something that can be saved')
    const opts: Electron.OpenDialogOptions = {
      title: `Save ${list.length} files to…`,
      buttonLabel: 'Save Here',
      defaultPath: app.getPath('music'),
      properties: ['openDirectory', 'createDirectory'],
    }
    const r = win ? await dialog.showOpenDialog(win, opts) : await dialog.showOpenDialog(opts)
    if (r.canceled || !r.filePaths[0]) return null
    const folder = r.filePaths[0]
    let last = ''
    for (const it of list) {
      // Never over another file: "Song (E major) 2.mp3".
      const ext = path.extname(it.name)
      let target = path.join(folder, it.name)
      for (let n = 2; fs.existsSync(target); n++) target = path.join(folder, `${path.basename(it.name, ext)} ${n}${ext}`)
      await download(it.apiPath, target)
      last = target
    }
    if (last) shell.showItemInFolder(last)
    return folder
  })

  handle('library:reveal', async (songId?: unknown) => {
    if (songId === undefined || songId === null) return void (await shell.openPath(libraryRoot()))
    if (typeof songId !== 'string' || !/^[0-9a-f]{32}$/.test(songId)) throw new Error('Bad song id')
    await shell.openPath(path.join(libraryRoot(), 'songs', songId))
  })

  handle('updates:info', () => ({ version: app.getVersion(), hasToken: updates.hasToken(), blocker: updates.blocker(), packageBlocker: packages.blocker() }))
  handle('updates:set-token', (token: unknown) => updates.setToken(token))
  handle('updates:check', () => updates.check())
  handle('updates:install', () => updates.install(win, () => engine.stop()))
  // Update packages (zips) and the version kept from before the last update.
  handle('updates:pick-package', async () => {
    const opts: Electron.OpenDialogOptions = {
      title: 'Install an Update Package',
      buttonLabel: 'Open',
      properties: ['openFile'],
      filters: [{ name: 'KeyFinder update package', extensions: ['zip'] }],
    }
    const r = win ? await dialog.showOpenDialog(win, opts) : await dialog.showOpenDialog(opts)
    if (r.canceled || !r.filePaths[0]) return null
    return packages.inspect(r.filePaths[0])
  })
  handle('updates:discard-package', () => packages.discard())
  handle('updates:install-package', () => packages.install(() => engine.stop()))
  handle('updates:previous', () => packages.previous())
  handle('updates:revert', () => packages.revert(() => engine.stop()))
  handle('updates:take-result', () => packages.takeResult())
}

// ------------------------------------------------------------ opened files

/** Songs opened with KeyFinder (Open With, dropping on the Dock icon, the command line on Windows). */
function openFiles(paths: string[]) {
  const media = new Set([...AUDIO_EXTENSIONS, ...VIDEO_EXTENSIONS, 'zip'])
  openedFiles.push(...paths.filter((p) => path.isAbsolute(p) && media.has(path.extname(p).slice(1).toLowerCase())))
  if (win && !win.webContents.isLoading()) flushOpenedFiles()
}

function flushOpenedFiles() {
  if (!openedFiles.length || !win) return
  win.webContents.send('open-files', openedFiles)
  openedFiles = []
  if (win.isMinimized()) win.restore()
  win.focus()
}

// --------------------------------------------------------------- lifecycle

function setupPermissions() {
  // Nothing KeyFinder does needs the camera, microphone, location or notifications.
  session.defaultSession.setPermissionRequestHandler((_wc, _permission, cb) => cb(false))
  session.defaultSession.setPermissionCheckHandler(() => false)
}

app.on('open-file', (e, file) => {
  e.preventDefault()
  openFiles([file])
})

if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', (_e, argv) => {
    openFiles(argv.slice(1))
    if (!win) return
    if (win.isMinimized()) win.restore()
    win.focus()
  })

  void app.whenReady().then(() => {
    engine = new Engine(libraryRoot(), path.join(app.getPath('userData'), 'models'))
    engine.onStatus((info) => win?.webContents.send('engine:status', info))
    engine.start()
    registerAppProtocol()
    setupPermissions()
    registerIpc()
    buildMenu()
    createWindow()
    if (process.platform === 'win32') openFiles(process.argv.slice(1))
    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow()
    })
  })

  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit()
  })
  app.on('will-quit', () => engine?.stop())
}
