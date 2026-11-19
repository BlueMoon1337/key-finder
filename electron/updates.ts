// The Update button (adapted from Player's): new versions of KeyFinder come from the GitHub repository's releases, which a
// GitHub Actions workflow builds and signs (.github/workflows/release.yml). The repository is
// public, so no token is needed; one can still be added (for a private repository, or more checks
// an hour than GitHub allows without one). It's kept in a file of its own in KeyFinder's settings
// folder and never handed to the page.
//
// Each release carries latest.json: the version, its notes, and for each platform the file to
// download, its SHA-512 and an Ed25519 signature over both. KeyFinder refuses any download whose
// hash or signature doesn't match the public key below, installs it and restarts.

import { type BrowserWindow, app, net } from 'electron'
import { spawn } from 'node:child_process'
import { createHash, createPublicKey, verify } from 'node:crypto'
import fs from 'node:fs'
import fsp from 'node:fs/promises'
import path from 'node:path'
import { pipeline } from 'node:stream/promises'
import { Readable, Transform } from 'node:stream'
import { swapInDownloaded } from './packages'
import publicKeyPem from './update-key.pem'

/** Where releases come from. */
export const REPOSITORY = 'BlueMoon1337/key-finder'

/**
 * Which build this computer needs. Mac builds are per processor (the engine inside is native
 * code), so the key carries the architecture: darwin-arm64, darwin-x64, win32-x64.
 */
export const PLATFORM_KEY = `${process.platform}-${process.arch}`

const PUBLIC_KEY = createPublicKey(publicKeyPem)

export interface Found {
  version: string
  current: string
  notes: string | null
  date: string | null
}

interface PlatformEntry {
  file: string
  sha512: string
  signature: string
}

interface Manifest {
  version: string
  notes?: string
  date?: string
  platforms: Partial<Record<string, PlatformEntry>>
}

interface Asset {
  name: string
  /** The API address, which downloads with the token (the browser address doesn't, for a private repository). */
  url: string
}

/** What's signed for each file. The release script (scripts/sign-update.mjs) builds the same text. */
export function signedMessage(version: string, platform: string, file: string, sha512: string) {
  return `KeyFinder update\n${version}\n${platform}\n${file}\n${sha512}`
}

/** GitHub's API, or a stand-in for trying updates (signatures are checked either way). */
function api() {
  return (process.env.KEYFINDER_UPDATE_API || 'https://api.github.com').replace(/\/$/, '')
}

const tokenPath = () => path.join(app.getPath('userData'), 'update-token')

function readToken(): string | null {
  try {
    const t = fs.readFileSync(tokenPath(), 'utf8').trim()
    return t || null
  } catch {
    return null
  }
}

export function hasToken() {
  return readToken() !== null
}

/** Keeps the GitHub token (readable only by this user); an empty one forgets it. */
export async function setToken(token: unknown) {
  const t = typeof token === 'string' ? token.trim() : ''
  if (!t) {
    await fsp.rm(tokenPath(), { force: true })
    return
  }
  if (/[\s\u0000-\u001f]/.test(t) || t.length > 400) throw new Error('That doesn’t look like a GitHub token.')
  await fsp.mkdir(path.dirname(tokenPath()), { recursive: true })
  await fsp.writeFile(tokenPath(), t, { mode: 0o600 })
}

/**
 * Why updates can't install here, if they can't:
 * - "translocated": macOS runs an app downloaded from the internet, and not notarized, from a
 *   temporary read-only copy until the download mark is taken off; an update can't replace it.
 * - "development": not a packaged build (npm run dev), so there's nothing to replace.
 */
export function blocker(): string | null {
  if (!app.isPackaged) return 'development'
  if (process.platform === 'darwin' && process.execPath.includes('/AppTranslocation/')) return 'translocated'
  if (process.platform === 'linux') return 'development'
  return null
}

/** 1.2.10 > 1.2.9; anything after a "-" (pre-release) is ignored. */
export function newer(a: string, b: string) {
  const parse = (v: string) => v.replace(/^v/, '').split('-')[0].split('.').map((n) => Number(n) || 0)
  const [x, y] = [parse(a), parse(b)]
  for (let i = 0; i < 3; i++) if ((x[i] ?? 0) !== (y[i] ?? 0)) return (x[i] ?? 0) > (y[i] ?? 0)
  return false
}

interface GitHubResponse {
  status: number
  headers: Record<string, string | string[]>
  body: Readable
}

const readAll = async (body: Readable) => {
  const chunks: Buffer[] = []
  for await (const c of body) chunks.push(c as Buffer)
  return Buffer.concat(chunks).toString('utf8')
}

/** One request through Chromium's network stack (system proxy settings apply), not following redirects. */
function request(url: string, headers: Record<string, string>): Promise<GitHubResponse | { redirect: string }> {
  return new Promise((resolve, reject) => {
    const req = net.request({ url, redirect: 'manual', headers })
    req.on('redirect', (_status, _method, redirectUrl) => {
      req.abort()
      resolve({ redirect: redirectUrl })
    })
    req.on('response', (res) => resolve({ status: res.statusCode, headers: res.headers, body: res as unknown as Readable }))
    req.on('error', reject)
    req.end()
  })
}

/**
 * Fetches from GitHub, following redirects by hand: release downloads redirect to a storage host,
 * which must not be sent the token.
 */
async function github(url: string, token: string | null, accept: string): Promise<GitHubResponse> {
  const origin = new URL(api()).origin
  for (let hops = 0; hops < 5; hops++) {
    const res = await request(url, {
      Accept: accept,
      'User-Agent': 'KeyFinder',
      'X-GitHub-Api-Version': '2022-11-28',
      ...(token && new URL(url).origin === origin ? { Authorization: `Bearer ${token}` } : {}),
    })
    if ('redirect' in res) {
      url = new URL(res.redirect, url).toString()
      continue
    }
    return res
  }
  throw new Error('GitHub redirected too many times.')
}

async function latestRelease(token: string | null): Promise<{ tag: string; assets: Asset[] }> {
  let res: GitHubResponse
  try {
    res = await github(`${api()}/repos/${REPOSITORY}/releases/latest`, token, 'application/vnd.github+json')
  } catch (e) {
    throw new Error(`Couldn’t reach GitHub: ${(e as Error).message}`)
  }
  if (res.status === 401) {
    throw new Error('GitHub didn’t accept the token. It may have expired: make a new one and paste it in, or remove it.')
  }
  if (res.status === 403 || res.status === 429) {
    throw new Error(
      token
        ? `GitHub refused (${res.status}): the token may not be able to read ${REPOSITORY}, or too many checks were made. Try again later.`
        : 'GitHub’s limit for checks without a token was reached for now. Try again in an hour, or add a token.',
    )
  }
  if (res.status === 404) {
    throw new Error(
      token
        ? `No release found. Either none has been published yet, or the token can’t read ${REPOSITORY} (it needs Contents: Read-only on that repository).`
        : `No release found. Either none has been published yet, or ${REPOSITORY} is private: then add a token.`,
    )
  }
  if (res.status !== 200) throw new Error(`GitHub answered with an error (${res.status}). Try again later.`)
  const body = JSON.parse(await readAll(res.body)) as { tag_name: string; assets: Asset[] }
  return { tag: body.tag_name, assets: body.assets ?? [] }
}

/** The update found by the last check, ready to install. */
let pending: { found: Found; entry: PlatformEntry; asset: Asset } | null = null

/** Looks for a newer version. Returns it, or null when KeyFinder is up to date. */
export async function check(): Promise<Found | null> {
  const token = readToken()
  const release = await latestRelease(token)
  const current = app.getVersion()
  pending = null
  // A release published without update files (no signing key at the time) is fine when it's
  // this version or older: there's nothing to install either way.
  if (!newer(release.tag, current)) return null
  const manifestAsset = release.assets.find((a) => a.name === 'latest.json')
  if (!manifestAsset) {
    throw new Error(`${release.tag} has no update files yet. It may still be building: try again in a few minutes.`)
  }
  const res = await github(manifestAsset.url, token, 'application/octet-stream')
  if (res.status !== 200) throw new Error(`Couldn’t read the update details (${res.status}).`)
  let manifest: Manifest
  try {
    manifest = JSON.parse(await readAll(res.body))
  } catch {
    throw new Error('The update details couldn’t be read.')
  }
  if (!manifest?.version || !newer(manifest.version, current)) return null
  const entry = manifest.platforms?.[PLATFORM_KEY]
  if (!entry?.file || !entry.sha512 || !entry.signature) {
    throw new Error(`KeyFinder ${manifest.version} has no download for this computer.`)
  }
  const asset = release.assets.find((a) => a.name === entry.file)
  if (!asset) throw new Error(`${release.tag} is missing ${entry.file}.`)
  const found: Found = {
    version: manifest.version,
    current,
    notes: manifest.notes?.trim() || null,
    date: manifest.date ? manifest.date.slice(0, 10) : null,
  }
  pending = { found, entry, asset }
  return found
}

/** Downloads to the updates folder, hashing as it goes. */
async function download(asset: Asset, token: string | null, file: string, onProgress: (received: number, total: number | null) => void) {
  const res = await github(asset.url, token, 'application/octet-stream')
  if (res.status !== 200) throw new Error(`Couldn’t download the update (${res.status}).`)
  const total = Number(res.headers['content-length']) || null
  const hash = createHash('sha512')
  let received = 0
  let lastReport = 0
  const meter = new Transform({
    transform(chunk: Buffer, _enc, done) {
      hash.update(chunk)
      received += chunk.length
      const now = Date.now()
      if (now - lastReport > 100) {
        lastReport = now
        onProgress(received, total)
      }
      done(null, chunk)
    },
  })
  await pipeline(res.body, meter, fs.createWriteStream(file))
  onProgress(received, total)
  return hash.digest('hex')
}

/**
 * Downloads the update found by the last check, checks its hash and signature, installs it and
 * restarts KeyFinder. `beforeRestart` runs just before quitting.
 */
export async function install(win: BrowserWindow | null, beforeRestart: () => void) {
  const why = blocker()
  if (why === 'translocated') {
    throw new Error('macOS is running KeyFinder from a temporary read-only copy, so it can’t be updated. Follow the steps above, then try again.')
  }
  if (why === 'development') throw new Error('Updates install only in the packaged app.')
  if (!pending) throw new Error('Check for updates first.')
  const token = readToken()
  const { found, entry, asset } = pending

  const dir = path.join(app.getPath('userData'), 'updates')
  await fsp.rm(dir, { recursive: true, force: true })
  await fsp.mkdir(dir, { recursive: true })
  const file = path.join(dir, path.basename(entry.file))
  const sha512 = await download(asset, token, file, (received, total) =>
    win?.webContents.send('updates:progress', { received, total }),
  )

  const signature = Buffer.from(entry.signature, 'base64')
  const signedOk = verify(null, Buffer.from(signedMessage(found.version, PLATFORM_KEY, entry.file, entry.sha512)), PUBLIC_KEY, signature)
  if (sha512 !== entry.sha512.toLowerCase() || !signedOk) {
    await fsp.rm(dir, { recursive: true, force: true })
    throw new Error('The download doesn’t match its signature, so it wasn’t installed. Try again later.')
  }

  if (process.platform === 'darwin') await installMac(file, dir, found.version)
  else await swapInDownloaded(file, found.version)

  pending = null
  beforeRestart()
  app.quit()
}

/**
 * macOS: unpack the new KeyFinder.app; once this one has quit, it's swapped in (this one kept for
 * Go Back, see packages.ts) and opened. On Windows the installer runs once KeyFinder has quit.
 */
async function installMac(zip: string, dir: string, version: string) {
  const unpacked = path.join(dir, 'unpacked')
  await run('/usr/bin/ditto', ['-x', '-k', zip, unpacked])
  const newApp = (await fsp.readdir(unpacked)).find((n) => n.endsWith('.app'))
  if (!newApp) throw new Error('The update didn’t contain KeyFinder.app.')
  await swapInDownloaded(path.join(unpacked, newApp), version)
}

function run(cmd: string, args: string[]) {
  return new Promise<void>((resolve, reject) => {
    const p = spawn(cmd, args, { stdio: 'ignore' })
    p.on('error', reject)
    p.on('exit', (code) => (code === 0 ? resolve() : reject(new Error(`${path.basename(cmd)} failed (${code})`))))
  })
}
