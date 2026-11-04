// Saves a copy of KeyFinder itself, as it's installed on this computer, to give to someone or to
// take to another computer: a .dmg (with the usual "drag to Applications" window) or a .zip on a
// Mac, a .zip of the installed app on Windows. Only the app goes in: not the library, settings,
// the update token or the downloaded models, which stay with each person's own copy.
//
// The copy is for the same kind of computer as this one (Apple silicon or Intel, Windows), and is
// signed the same way (ad hoc on a Mac), so the first time it's opened it needs the same
// right-click ▸ Open (Mac) or More info ▸ Run anyway (Windows) as a download from Releases.

import { spawn } from 'node:child_process'
import fs from 'node:fs'
import fsp from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { type BrowserWindow, app, dialog, shell } from 'electron'

export type CopyFormat = 'dmg' | 'zip'

/** The formats this computer can make. */
export function copyFormats(): CopyFormat[] {
  if (process.platform === 'darwin') return ['dmg', 'zip']
  if (process.platform === 'win32') return ['zip']
  return []
}

/** Why a copy can't be made here, if it can't: 'development' when running from source. */
export function copyBlocker(): string | null {
  return app.isPackaged ? null : 'development'
}

/** What's copied: KeyFinder.app on a Mac, the folder KeyFinder is installed in on Windows. */
function installed(): string {
  return process.platform === 'darwin' ? path.resolve(process.execPath, '..', '..', '..') : path.dirname(process.execPath)
}

/** Named as the release files are, so it's clear which computers it's for. */
function fileName(format: CopyFormat) {
  const v = app.getVersion()
  return process.platform === 'darwin' ? `KeyFinder-${v}-${process.arch}-mac.${format}` : `KeyFinder-${v}-win-${process.arch}.zip`
}

function run(cmd: string, args: string[]): Promise<void> {
  return new Promise((resolve, reject) => {
    const p = spawn(cmd, args, { windowsHide: true })
    let err = ''
    p.stderr.on('data', (d) => (err = (err + d).slice(-2000)))
    p.on('error', reject)
    p.on('close', (code) => (code === 0 ? resolve() : reject(new Error(err.trim() || `${cmd} exited with ${code}`))))
  })
}

async function makeDmg(bundle: string, dest: string) {
  // A folder holding the app and a link to /Applications becomes the disk image's window.
  const staging = await fsp.mkdtemp(path.join(os.tmpdir(), 'keyfinder-dmg-'))
  try {
    const copy = path.join(staging, 'KeyFinder.app')
    // On APFS, cp -c clones the app (instant, no extra space); elsewhere ditto copies it.
    await run('/bin/cp', ['-cR', bundle, copy]).catch(() => run('/usr/bin/ditto', [bundle, copy]))
    await fsp.symlink('/Applications', path.join(staging, 'Applications'))
    await run('/usr/bin/hdiutil', ['create', '-volname', `KeyFinder ${app.getVersion()}`, '-srcfolder', staging, '-ov', '-format', 'UDZO', dest])
  } finally {
    await fsp.rm(staging, { recursive: true, force: true })
  }
}

async function makeZip(source: string, dest: string) {
  if (process.platform === 'darwin') {
    // ditto keeps the bundle's symlinks, permissions and signature, which a plain zip would break.
    return run('/usr/bin/ditto', ['-c', '-k', '--sequesterRsrc', '--keepParent', source, dest])
  }
  // Windows 10 and 11 ship bsdtar, which writes a zip when the name ends in .zip. The uninstaller
  // belongs to this installation, not the copy.
  const tar = path.join(process.env.SystemRoot ?? 'C:\\Windows', 'System32', 'tar.exe')
  const args = ['-a', '-c', '-f', dest, '--exclude', 'Uninstall KeyFinder.exe', '-C', path.dirname(source), path.basename(source)]
  if (fs.existsSync(tar)) return run(tar, args)
  const ps = `Compress-Archive -Path '${source.replace(/'/g, "''")}' -DestinationPath '${dest.replace(/'/g, "''")}' -Force`
  return run('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', ps])
}

/**
 * Asks where to save, then makes the copy there. Resolves to the saved path, or null if cancelled.
 * Shows the file in Finder / Explorer when it's done.
 */
export async function saveCopy(win: BrowserWindow | null, format: CopyFormat): Promise<string | null> {
  if (copyBlocker()) throw new Error('A copy can be saved only from the installed app, not when running from source.')
  if (!copyFormats().includes(format)) throw new Error(`KeyFinder can’t be saved as a .${format} on this computer.`)
  const opts: Electron.SaveDialogOptions = {
    title: 'Save a Copy of KeyFinder',
    defaultPath: path.join(app.getPath('desktop'), fileName(format)),
    filters: [{ name: format === 'dmg' ? 'Disk Image' : 'ZIP Archive', extensions: [format] }],
  }
  const r = win ? await dialog.showSaveDialog(win, opts) : await dialog.showSaveDialog(opts)
  if (r.canceled || !r.filePath) return null
  const dest = r.filePath.toLowerCase().endsWith(`.${format}`) ? r.filePath : `${r.filePath}.${format}`
  // Made next to the destination under another name, so a failure never leaves half a file there.
  const partial = `${dest.slice(0, -format.length - 1)}.partial.${format}`
  await fsp.rm(partial, { force: true })
  try {
    if (format === 'dmg') await makeDmg(installed(), partial)
    else await makeZip(installed(), partial)
    await fsp.rm(dest, { force: true })
    await fsp.rename(partial, dest)
  } catch (e) {
    await fsp.rm(partial, { force: true })
    throw new Error(`Couldn’t save a copy of KeyFinder: ${(e as Error).message}`)
  }
  shell.showItemInFolder(dest)
  return dest
}
