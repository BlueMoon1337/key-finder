// Runs the version-swap scripts (electron/swap-scripts.ts) on this computer, on scratch folders,
// the way KeyFinder runs them when it updates or goes back, and checks what they did: the new
// version is in, the one before is kept, the result is recorded, failures change nothing.
// CI runs it on Windows, macOS and Linux:  node scripts/check-swap-scripts.mjs

import { buildSync } from 'esbuild'
import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

const out = buildSync({ entryPoints: ['electron/swap-scripts.ts'], bundle: true, format: 'esm', platform: 'node', write: false })
const { POSIX_SCRIPT, WINDOWS_SCRIPT } = await import(`data:text/javascript;base64,${Buffer.from(out.outputFiles[0].text).toString('base64')}`)

const win = process.platform === 'win32'
const mac = process.platform === 'darwin'
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'keyfinder-swap-'))
let failures = 0
const check = (ok, what) => {
  console.log(`${ok ? '✓' : '✗'} ${what}`)
  if (!ok) failures++
}
const read = (f) => (fs.existsSync(f) ? fs.readFileSync(f, 'utf8') : null)
const write = (f, text) => {
  fs.mkdirSync(path.dirname(f), { recursive: true })
  fs.writeFileSync(f, text)
}

// A process that has already ended, standing in for KeyFinder after it quits.
const gone = spawnSync(process.execPath, ['-e', '0']).pid

const versions = path.join(root, 'versions')
const files = {
  prev: path.join(versions, 'previous'),
  meta: path.join(versions, 'previous.json'),
  result: path.join(versions, 'result.json'),
  lock: path.join(versions, 'swapping'),
}

/** Runs the script as startSwap() would, and returns the result it recorded. */
function swap({ kind, action = 'update', target, source, payload, version, keptVersion, bundle = '' }) {
  fs.mkdirSync(versions, { recursive: true })
  fs.rmSync(files.result, { force: true })
  fs.writeFileSync(files.lock, String(Date.now()))
  const env = {
    ...process.env,
    KF_PID: String(gone),
    KF_KIND: kind,
    KF_ACTION: action,
    KF_TARGET: target,
    KF_SOURCE: source,
    KF_PREV: files.prev,
    KF_PREV_PAYLOAD: payload,
    KF_META: JSON.stringify({ version: keptVersion, kind: kind === 'installer' ? 'dir' : kind, savedAt: 1, replacedBy: version }),
    KF_META_FILE: files.meta,
    KF_RESULT: files.result,
    KF_LOCK: files.lock,
    KF_VERSION: version,
    KF_HASH: '',
    KF_BUNDLE: bundle,
    // Something harmless to "open again".
    KF_EXE: win ? path.join(process.env.SystemRoot ?? 'C:\\Windows', 'System32', 'whoami.exe') : '/usr/bin/true',
  }
  const r = win
    ? spawnSync('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', Buffer.from(WINDOWS_SCRIPT, 'utf16le').toString('base64')], { env, encoding: 'utf8' })
    : spawnSync('/bin/sh', ['-c', POSIX_SCRIPT], { env, encoding: 'utf8' })
  if (r.status !== 0 || r.error) console.log(`  (exit ${r.status}) ${r.error ?? ''} ${r.stderr ?? ''}`.trim())
  const result = read(files.result)
  check(!fs.existsSync(files.lock), `${kind} ${action}: the lock is removed`)
  return result ? JSON.parse(result) : null
}

// ------------------------------------------------------------------ an interface (app.asar)

// On macOS the interface sits in a bundle whose Info.plist the script updates.
const bundle = mac ? path.join(root, 'apps', 'KeyFinder.app') : ''
const asar = mac ? path.join(bundle, 'Contents', 'Resources', 'app.asar') : path.join(root, 'app', 'resources', 'app.asar')
write(asar, 'interface 1.0')
if (mac) {
  write(
    path.join(bundle, 'Contents', 'Info.plist'),
    '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0"><dict><key>CFBundleShortVersionString</key><string>1.0</string><key>CFBundleVersion</key><string>1.0</string></dict></plist>\n',
  )
}
const incoming = path.join(root, 'staged', 'app.asar')
write(incoming, 'interface 2.0')

let r = swap({ kind: 'interface', target: asar, source: incoming, payload: 'app.asar', version: '2.0', keptVersion: '1.0', bundle })
check(r?.ok === true && r.action === 'update' && r.version === '2.0', `interface update reports success (${JSON.stringify(r)})`)
check(read(asar) === 'interface 2.0', 'the new interface is in place')
check(read(path.join(files.prev, 'app.asar')) === 'interface 1.0', 'the old interface is kept')
check(JSON.parse(read(files.meta) ?? '{}').version === '1.0', 'previous.json names the kept version')
if (mac) {
  const v = spawnSync('/usr/libexec/PlistBuddy', ['-c', 'Print :CFBundleShortVersionString', path.join(bundle, 'Contents', 'Info.plist')], { encoding: 'utf8' }).stdout.trim()
  check(v === '2.0', `Info.plist says the new version (${v})`)
}

r = swap({ kind: 'interface', action: 'revert', target: asar, source: path.join(files.prev, 'app.asar'), payload: 'app.asar', version: '1.0', keptVersion: '2.0', bundle })
check(r?.ok === true && r.action === 'revert', `interface go back reports success (${JSON.stringify(r)})`)
check(read(asar) === 'interface 1.0', 'going back puts the old interface back')
check(read(path.join(files.prev, 'app.asar')) === 'interface 2.0', 'and keeps the newer one to come back to')

r = swap({ kind: 'interface', target: asar, source: path.join(root, 'missing.asar'), payload: 'app.asar', version: '3.0', keptVersion: '1.0', bundle })
check(r?.ok === false && !!r.message, `a failed update says so (${r?.message})`)
check(read(asar) === 'interface 1.0', 'and changes nothing')
check(read(path.join(files.prev, 'app.asar')) === 'interface 2.0', 'and keeps the previous version as it was')

// ------------------------------------------------------------------ a whole app

if (win) {
  // The install folder, swapped back from a kept copy (Go Back after an installer update).
  const install = path.join(root, 'install')
  write(path.join(install, 'KeyFinder.exe'), 'app 1.0')
  write(path.join(install, 'resources', 'app.asar'), 'interface 1.0')
  const kept = path.join(root, 'kept', 'app')
  write(path.join(kept, 'KeyFinder.exe'), 'app 0.9')
  write(path.join(kept, 'resources', 'app.asar'), 'interface 0.9')
  r = swap({ kind: 'dir', action: 'revert', target: install, source: kept, payload: 'app', version: '0.9', keptVersion: '1.0' })
  check(r?.ok === true, `folder go back reports success (${JSON.stringify(r)})`)
  check(read(path.join(install, 'KeyFinder.exe')) === 'app 0.9', 'the kept app is back in the install folder')
  check(read(path.join(files.prev, 'app', 'KeyFinder.exe')) === 'app 1.0', 'and the one it replaced is kept')

  // The installer: the folder is kept first, then it runs (here a script standing in for it).
  const setup = path.join(root, 'KeyFinder-Setup-2.0.cmd')
  fs.writeFileSync(setup, '@echo off\r\necho app 2.0> "%KF_TARGET%\\KeyFinder.exe"\r\nexit /b 0\r\n')
  r = swap({ kind: 'installer', target: install, source: setup, payload: 'app', version: '2.0', keptVersion: '0.9' })
  check(r?.ok === true, `installer update reports success (${JSON.stringify(r)})`)
  check(read(path.join(install, 'KeyFinder.exe'))?.trim() === 'app 2.0', 'the installer ran')
  check(read(path.join(files.prev, 'app', 'KeyFinder.exe')) === 'app 0.9', 'the version before it is kept')

  const broken = path.join(root, 'KeyFinder-Setup-3.0.cmd')
  fs.writeFileSync(broken, '@echo off\r\nexit /b 2\r\n')
  r = swap({ kind: 'installer', target: install, source: broken, payload: 'app', version: '3.0', keptVersion: '2.0' })
  check(r?.ok === false && /code 2/.test(r.message), `a failed installer says so (${r?.message})`)
} else {
  // A whole app folder swapped (KeyFinder.app on macOS; any folder works the same way).
  const app = path.join(root, 'Applications', 'KeyFinder.app')
  write(path.join(app, 'marker'), 'app 1.0')
  const staged = path.join(root, 'download', 'KeyFinder.app')
  write(path.join(staged, 'marker'), 'app 2.0')
  r = swap({ kind: 'bundle', target: app, source: staged, payload: 'KeyFinder.app', version: '2.0', keptVersion: '1.0' })
  check(r?.ok === true, `app update reports success (${JSON.stringify(r)})`)
  check(read(path.join(app, 'marker')) === 'app 2.0', 'the new app is in place')
  check(read(path.join(files.prev, 'KeyFinder.app', 'marker')) === 'app 1.0', 'the old app is kept')
  r = swap({ kind: 'bundle', action: 'revert', target: app, source: path.join(files.prev, 'KeyFinder.app'), payload: 'KeyFinder.app', version: '1.0', keptVersion: '2.0' })
  check(r?.ok === true && read(path.join(app, 'marker')) === 'app 1.0', 'going back puts the old app back')
  check(read(path.join(files.prev, 'KeyFinder.app', 'marker')) === 'app 2.0', 'and keeps the newer one')
}

fs.rmSync(root, { recursive: true, force: true })
console.log(failures ? `${failures} failed` : 'all passed')
process.exit(failures ? 1 : 0)
