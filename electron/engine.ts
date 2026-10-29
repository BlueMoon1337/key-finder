// The analysis engine: KeyFinder's Python side (keyfinder/engine.py), run as a child process.
//
// It listens on a free port on 127.0.0.1 and answers only requests carrying this launch's random
// token, which the app:// protocol adds on the way (main.ts), so nothing else on the computer can
// use it. It exits by itself when its stdin closes, i.e. when KeyFinder quits or crashes.

import { app } from 'electron'
import { type ChildProcessWithoutNullStreams, spawn } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import type { EngineInfo, EngineStatus } from '../src/platform/types'

const READY = 'KEYFINDER_ENGINE_READY'
/** The first start of a packaged engine can be slow while macOS checks its files. */
const START_TIMEOUT_MS = 90_000
const MAX_RESTARTS = 3
const LOG_LINES = 40

interface Command {
  cmd: string
  args: string[]
  cwd?: string
}

/** The frozen engine inside the app, or `python -m keyfinder.engine` from the repository in development. */
function engineCommand(): Command {
  if (process.env.KEYFINDER_ENGINE) return { cmd: process.env.KEYFINDER_ENGINE, args: [] }
  if (app.isPackaged) {
    const exe = process.platform === 'win32' ? 'keyfinder-engine.exe' : 'keyfinder-engine'
    return { cmd: path.join(process.resourcesPath, 'engine', exe), args: [] }
  }
  const repo = path.resolve(__dirname, '..')
  const venv = process.platform === 'win32' ? path.join(repo, '.venv', 'Scripts', 'python.exe') : path.join(repo, '.venv', 'bin', 'python')
  const python = fs.existsSync(venv) ? venv : process.platform === 'win32' ? 'python' : 'python3'
  return { cmd: python, args: ['-m', 'keyfinder.engine'], cwd: repo }
}

export class Engine {
  readonly token = randomBytes(32).toString('hex')
  private child: ChildProcessWithoutNullStreams | null = null
  private port: number | null = null
  private version: string | null = null
  private status: EngineStatus = 'starting'
  private error: string | null = null
  private log: string[] = []
  private restarts = 0
  private stopping = false
  private waiters: { resolve: (port: number) => void; reject: (e: Error) => void }[] = []
  private listeners = new Set<(info: EngineInfo) => void>()

  constructor(readonly libraryPath: string) {}

  info(): EngineInfo {
    return { status: this.status, error: this.error, version: this.version, libraryPath: this.libraryPath }
  }

  onStatus(fn: (info: EngineInfo) => void) {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }

  /** The port once the engine is up; waits for it while it starts. */
  ready(): Promise<number> {
    if (this.status === 'ready' && this.port) return Promise.resolve(this.port)
    if (this.status === 'failed') return Promise.reject(new Error(this.error ?? 'The engine is not running.'))
    return new Promise((resolve, reject) => this.waiters.push({ resolve, reject }))
  }

  start() {
    this.stopping = false
    fs.mkdirSync(this.libraryPath, { recursive: true })
    const { cmd, args, cwd } = engineCommand()
    this.setStatus(this.restarts ? 'restarting' : 'starting', null)
    this.log = []
    let child: ChildProcessWithoutNullStreams
    try {
      child = spawn(cmd, [...args, '--data', this.libraryPath], {
        cwd,
        env: { ...process.env, KEYFINDER_TOKEN: this.token, PYTHONUNBUFFERED: '1' },
        stdio: 'pipe',
        windowsHide: true,
      })
    } catch (e) {
      this.fail(`Couldn’t start the engine (${cmd}): ${(e as Error).message}`)
      return
    }
    this.child = child
    const timer = setTimeout(() => {
      if (this.status !== 'ready') {
        this.fail('The engine took too long to start.')
        child.kill()
      }
    }, START_TIMEOUT_MS)

    let buffered = ''
    child.stdout.setEncoding('utf8')
    child.stdout.on('data', (chunk: string) => {
      buffered += chunk
      let nl: number
      while ((nl = buffered.indexOf('\n')) >= 0) {
        const line = buffered.slice(0, nl).trim()
        buffered = buffered.slice(nl + 1)
        if (line.startsWith(READY)) {
          clearTimeout(timer)
          try {
            const { port, version } = JSON.parse(line.slice(READY.length))
            this.port = port
            this.version = version
            this.restarts = 0
            this.setStatus('ready', null)
            this.waiters.splice(0).forEach((w) => w.resolve(port))
          } catch {
            this.fail('The engine started but its address couldn’t be read.')
          }
        } else if (line) this.remember(line)
      }
    })
    child.stderr.setEncoding('utf8')
    child.stderr.on('data', (chunk: string) => chunk.split('\n').forEach((l) => l.trim() && this.remember(l)))
    child.on('error', (e) => {
      clearTimeout(timer)
      this.fail(`Couldn’t start the engine (${cmd}): ${e.message}`)
    })
    child.on('exit', (code, signal) => {
      clearTimeout(timer)
      if (this.child === child) this.child = null
      this.port = null
      if (this.stopping) return
      // An engine that crashes is started again a few times before giving up.
      if (this.restarts < MAX_RESTARTS && this.status !== 'failed') {
        this.restarts++
        this.remember(`Engine stopped (${signal ?? code}); restarting.`)
        setTimeout(() => this.start(), 500 * this.restarts)
      } else if (this.status !== 'failed') {
        this.fail(`The engine stopped (${signal ?? `exit code ${code}`}).`)
      }
    })
  }

  async restart() {
    this.stop()
    this.restarts = 0
    this.status = 'starting'
    this.start()
  }

  stop() {
    this.stopping = true
    const child = this.child
    this.child = null
    if (!child) return
    // Closing stdin asks it to exit; kill it if it hasn't shortly after.
    child.stdin.end()
    setTimeout(() => {
      if (child.exitCode === null && child.signalCode === null) child.kill()
    }, 2000).unref()
  }

  private remember(line: string) {
    this.log.push(line)
    if (this.log.length > LOG_LINES) this.log.shift()
  }

  private fail(message: string) {
    const tail = this.log.slice(-8).join('\n')
    this.setStatus('failed', tail ? `${message}\n\n${tail}` : message)
    this.waiters.splice(0).forEach((w) => w.reject(new Error(message)))
  }

  private setStatus(status: EngineStatus, error: string | null) {
    this.status = status
    this.error = error
    const info = this.info()
    this.listeners.forEach((fn) => fn(info))
  }
}
