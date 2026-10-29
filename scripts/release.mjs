// Release steps for .github/workflows/release.yml (Node 22, no dependencies). From Player's
// scripts/release.mjs; platforms carry the processor (darwin-arm64, darwin-x64, win32-x64) because
// each KeyFinder build bundles a native engine.
//
//   node scripts/release.mjs sign <platform>   hash + sign this platform's update file → release/update-<platform>.json
//   node scripts/release.mjs upload            upload this platform's installers and update file to the draft release
//   node scripts/release.mjs publish <dir>     write latest.json from the update-*.json files in <dir>, publish the release
//
// sign needs UPDATE_SIGNING_KEY (the Ed25519 private key, PEM). upload/publish need GITHUB_TOKEN,
// GITHUB_REPOSITORY and RELEASE_ID; publish also needs TAG.

import { createHash, createPrivateKey, sign } from 'node:crypto'
import fs from 'node:fs'
import fsp from 'node:fs/promises'
import path from 'node:path'
import { pipeline } from 'node:stream/promises'

const version = JSON.parse(fs.readFileSync('package.json', 'utf8')).version
const RELEASE_DIR = 'release'

/** Must match signedMessage() in electron/updates.ts exactly. */
const signedMessage = (platform, file, sha512) => `KeyFinder update\n${version}\n${platform}\n${file}\n${sha512}`

/** The file the Update button installs on each platform, and what else is offered for download. */
const FILES = {
  'darwin-arm64': { update: /-arm64-mac\.zip$/, extra: [/-arm64-mac\.dmg$/] },
  'darwin-x64': { update: /-x64-mac\.zip$/, extra: [/-x64-mac\.dmg$/] },
  'win32-x64': { update: /^KeyFinder-Setup-.*\.exe$/, extra: [] },
}
/** This machine's platform key, as electron/updates.ts computes it. */
const HERE = `${process.platform}-${process.env.TARGET_ARCH || process.arch}`

function find(pattern) {
  const hits = fs.readdirSync(RELEASE_DIR).filter((f) => pattern.test(f))
  if (hits.length !== 1) throw new Error(`Expected one file matching ${pattern} in ${RELEASE_DIR}/, found: ${hits.join(', ') || 'none'}`)
  return hits[0]
}

async function sha512(file) {
  const hash = createHash('sha512')
  await pipeline(fs.createReadStream(file), hash)
  return hash.digest('hex')
}

async function signCmd(platform) {
  if (!FILES[platform]) throw new Error(`Unknown platform ${platform}`)
  if (!process.env.UPDATE_SIGNING_KEY) throw new Error('UPDATE_SIGNING_KEY is not set (see README ▸ Updates).')
  const key = createPrivateKey(process.env.UPDATE_SIGNING_KEY)
  const file = find(FILES[platform].update)
  const digest = await sha512(path.join(RELEASE_DIR, file))
  const signature = sign(null, Buffer.from(signedMessage(platform, file, digest)), key).toString('base64')
  const out = path.join(RELEASE_DIR, `update-${platform}.json`)
  await fsp.writeFile(out, JSON.stringify({ platform, file, sha512: digest, signature }, null, 2))
  console.log(`Signed ${file} → ${out}`)
}

function env(name) {
  const v = process.env[name]
  if (!v) throw new Error(`${name} is not set`)
  return v
}

async function gh(method, url, body, headers = {}) {
  const res = await fetch(url, {
    method,
    headers: {
      Authorization: `Bearer ${env('GITHUB_TOKEN')}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      ...headers,
    },
    body,
  })
  if (!res.ok) throw new Error(`${method} ${url} → ${res.status}: ${await res.text()}`)
  return res.status === 204 ? null : res.json()
}

async function uploadAsset(name, data, contentType = 'application/octet-stream') {
  const repo = env('GITHUB_REPOSITORY')
  const url = `https://uploads.github.com/repos/${repo}/releases/${env('RELEASE_ID')}/assets?name=${encodeURIComponent(name)}`
  await gh('POST', url, data, { 'Content-Type': contentType })
  console.log(`Uploaded ${name}`)
}

async function uploadCmd() {
  const { update, extra } = FILES[HERE]
  for (const pattern of [update, ...extra]) {
    const file = find(pattern)
    await uploadAsset(file, await fsp.readFile(path.join(RELEASE_DIR, file)))
  }
}

async function publishCmd(dir) {
  const repo = env('GITHUB_REPOSITORY')
  const releaseId = env('RELEASE_ID')
  const release = await gh('GET', `https://api.github.com/repos/${repo}/releases/${releaseId}`)
  const platforms = {}
  for (const f of await fsp.readdir(dir, { recursive: true })) {
    if (!/update-[a-z0-9-]+\.json$/.test(f)) continue
    const entry = JSON.parse(await fsp.readFile(path.join(dir, f), 'utf8'))
    platforms[entry.platform] = { file: entry.file, sha512: entry.sha512, signature: entry.signature }
  }
  for (const p of Object.keys(FILES)) if (!platforms[p]) throw new Error(`No signed update for ${p}`)
  const manifest = { version, notes: release.body ?? '', date: new Date().toISOString(), platforms }
  await uploadAsset('latest.json', JSON.stringify(manifest, null, 2), 'application/json')
  await gh('PATCH', `https://api.github.com/repos/${repo}/releases/${releaseId}`, JSON.stringify({ draft: false, make_latest: 'true' }))
  console.log(`Published ${env('TAG')}`)
}

const [cmd, arg] = process.argv.slice(2)
const run = { sign: () => signCmd(arg), upload: uploadCmd, publish: () => publishCmd(arg ?? 'signed') }[cmd]
if (!run) {
  console.error('Usage: node scripts/release.mjs sign <platform> | upload | publish <dir>')
  process.exit(2)
}
run().catch((e) => {
  console.error(`::error::${e.message}`)
  process.exit(1)
})
