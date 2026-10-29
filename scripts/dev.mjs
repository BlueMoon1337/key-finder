// Desktop dev loop (as in Player): Vite (with hot reload) for the UI, Electron pointed at it.
// Electron starts the engine itself, with the repository's .venv Python (see electron/engine.ts).
import { spawn } from 'node:child_process'
import { createRequire } from 'node:module'
import { createServer } from 'vite'

const server = await createServer({ server: { port: 5173, strictPort: true } })
await server.listen()
const url = server.resolvedUrls.local[0]

await import('./build-electron.mjs')

const electron = createRequire(import.meta.url)('electron')
const child = spawn(electron, ['.', ...process.argv.slice(2)], {
  stdio: 'inherit',
  env: { ...process.env, VITE_DEV_SERVER_URL: url },
})
child.on('exit', async (code) => {
  await server.close()
  process.exit(code ?? 0)
})
