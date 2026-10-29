// Browser dev loop: the engine as a plain web server on :8000, and Vite on :5173 proxying /api to it.
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { createServer } from 'vite'

const venv = process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python'
const python = fs.existsSync(venv) ? path.resolve(venv) : process.platform === 'win32' ? 'python' : 'python3'
const engine = spawn(python, ['-m', 'keyfinder', 'serve', '--port', '8000', '--data', 'data'], { stdio: 'inherit' })

const server = await createServer({ server: { port: 5173 } })
await server.listen()
server.printUrls()

const stop = async () => {
  engine.kill()
  await server.close()
  process.exit(0)
}
process.on('SIGINT', stop)
process.on('SIGTERM', stop)
engine.on('exit', (code) => {
  if (code) console.error(`The engine exited (${code}). Is the Python environment set up? See README ▸ Development.`)
})
