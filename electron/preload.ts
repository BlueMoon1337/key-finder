import { contextBridge, ipcRenderer, webUtils } from 'electron'
import type { DesktopAPI, EngineInfo, MenuCommand } from '../src/platform/types'

function listen<T>(channel: string, cb: (value: T) => void) {
  const listener = (_e: Electron.IpcRendererEvent, value: T) => cb(value)
  ipcRenderer.on(channel, listener)
  return () => {
    ipcRenderer.removeListener(channel, listener)
  }
}

const api: DesktopAPI = {
  platform: process.platform,
  apiBase: 'app://keyfinder',
  engine: {
    info: () => ipcRenderer.invoke('engine:info'),
    restart: () => ipcRenderer.invoke('engine:restart'),
    onStatus: (cb) => listen<EngineInfo>('engine:status', cb),
  },
  pickFiles: (source) => ipcRenderer.invoke('dialog:pick', source),
  pathForFile: (file) => webUtils.getPathForFile(file),
  saveFromApi: (apiPath, suggestedName) => ipcRenderer.invoke('file:save-from-api', apiPath, suggestedName),
  saveManyFromApi: (items) => ipcRenderer.invoke('file:save-many-from-api', items),
  reveal: (songId) => ipcRenderer.invoke('library:reveal', songId),
  onOpenFiles: (cb) => listen<string[]>('open-files', cb),
  onMenu: (cb) => listen<MenuCommand>('menu', cb),
  copy: {
    info: () => ipcRenderer.invoke('app:copy-info'),
    save: (format) => ipcRenderer.invoke('app:save-copy', format),
  },
  updates: {
    info: () => ipcRenderer.invoke('updates:info'),
    setToken: (token) => ipcRenderer.invoke('updates:set-token', token),
    check: () => ipcRenderer.invoke('updates:check'),
    install: () => ipcRenderer.invoke('updates:install'),
    onProgress: (cb) => listen('updates:progress', cb),
  },
}

contextBridge.exposeInMainWorld('keyfinderDesktop', api)
