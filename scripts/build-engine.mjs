// Freezes the Python engine with PyInstaller into build/engine-dist/keyfinder-engine/, which
// electron-builder copies into the app (electron-builder.yml ▸ extraResources).
import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

const venv = process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python'
const python = process.env.PYTHON || (fs.existsSync(venv) ? path.resolve(venv) : process.platform === 'win32' ? 'python' : 'python3')
const args = ['-m', 'PyInstaller', 'engine.spec', '--noconfirm', '--distpath', '../build/engine-dist', '--workpath', '../build/engine-work']
const r = spawnSync(python, args, { cwd: 'packaging', stdio: 'inherit' })
if (r.status !== 0) {
  console.error('PyInstaller failed. Install the build tools with: pip install -e ".[desktop]"')
  process.exit(r.status ?? 1)
}
const exe = path.join('build', 'engine-dist', 'keyfinder-engine', process.platform === 'win32' ? 'keyfinder-engine.exe' : 'keyfinder-engine')
if (!fs.existsSync(exe)) {
  console.error(`Expected ${exe} after the build.`)
  process.exit(1)
}
console.log(`Engine built: ${exe}`)
