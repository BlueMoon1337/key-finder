import { type ReactNode, useRef, useState } from 'react'
import type { SeparationMode } from '../api'
import { type ImportSource, desktop } from '../platform'
import { addFiles, addPaths, addUrl, errorMessage, setState, toast, updateSettings, useApp } from '../store'
import { ChevronLeftIcon, FilesTile, LinkTile, MusicTile, PhotosTile } from './Icons'
import { Sheet } from './Sheet'

const MEDIA_ACCEPT = 'audio/*,video/*,.mp3,.wav,.flac,.m4a,.aac,.aif,.aiff,.ogg,.wma,.mp4,.mov,.m4v'

/** In a browser each source is a file input; Camera Roll and Music narrow what it offers. */
const WEB_ACCEPT: Record<ImportSource, string> = {
  file: MEDIA_ACCEPT,
  camera: 'video/*',
  music: 'audio/*',
}

const SEPARATIONS: { value: SeparationMode; label: string }[] = [
  { value: '4stems', label: 'Vocals · Drums · Bass · Other' },
  { value: '2stems', label: 'Vocals · Accompaniment' },
  { value: '6stems', label: 'Vocals · Drums · Bass · Guitar · Piano · Other' },
  { value: 'none', label: 'No separation (key, tempo and chords only)' },
]

export function AddSongSheet() {
  const mode = useApp((s) => s.settings.mode)
  const caps = useApp((s) => s.capabilities)
  const [page, setPage] = useState<'sources' | 'url'>('sources')
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const close = () => setState({ addOpen: false })
  const hasDemucs = !!caps?.backends.includes('demucs')

  const pick = async (source: ImportSource) => {
    if (desktop) {
      const paths = await desktop.pickFiles(source)
      if (!paths.length) return
      close()
      await addPaths(paths)
      return
    }
    const el = input.current!
    el.accept = WEB_ACCEPT[source]
    el.click()
  }

  const importLink = async () => {
    if (!url.trim()) return
    setBusy(true)
    try {
      await addUrl(url.trim())
      close()
    } catch (e) {
      toast(errorMessage(e), true)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet title="Add a Song" onClose={close}>
      {page === 'sources' ? (
        <div className="sources">
          <Source tile={<FilesTile />} className="files" title="Import File" onClick={() => void pick('file')}>
            Songs from your computer, Google Drive, Dropbox, and more.
          </Source>
          <Source tile={<PhotosTile />} className="photos" title="Camera Roll" onClick={() => void pick('camera')}>
            Add media from your device’s gallery.
          </Source>
          <Source tile={<MusicTile />} className="music" title="Music" onClick={() => void pick('music')}>
            Songs saved in your music library (DRM-free files).
          </Source>
          <Source tile={<LinkTile />} className="cloud" title="Cloud Storage" onClick={() => setPage('url')}>
            Any media from cloud services or public URLs. Streaming links won’t work.
          </Source>
        </div>
      ) : (
        <form
          className="url-form"
          onSubmit={(e) => {
            e.preventDefault()
            void importLink()
          }}
        >
          <button type="button" className="text-btn" onClick={() => setPage('sources')}>
            <ChevronLeftIcon />
            Back
          </button>
          <label htmlFor="url-input">
            <strong>Paste a link</strong>
            <small>A public Google Drive or Dropbox share link, or a direct link to an audio or video file.</small>
          </label>
          <input id="url-input" type="url" autoFocus placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} />
          <button type="submit" className="pill-btn accent" disabled={!url.trim() || busy}>
            {busy ? 'Downloading…' : 'Import'}
          </button>
        </form>
      )}

      <label className="sheet-option">
        <span>Separate into</span>
        <select value={mode} onChange={(e) => updateSettings({ mode: e.target.value as SeparationMode })}>
          {SEPARATIONS.map((o) => (
            <option key={o.value} value={o.value} disabled={o.value === '6stems' && !hasDemucs}>
              {o.label}
              {o.value === '6stems' && !hasDemucs ? ' (needs Demucs)' : ''}
            </option>
          ))}
        </select>
      </label>

      <footer className="sheet-footer">
        <strong>Supported files</strong>
        <span>MP3, WAV, FLAC, M4A, MP4, MOV, WMA</span>
      </footer>

      <input
        ref={input}
        type="file"
        multiple
        hidden
        onChange={(e) => {
          const files = [...(e.target.files ?? [])]
          e.target.value = ''
          if (!files.length) return
          close()
          void addFiles(files)
        }}
      />
    </Sheet>
  )
}

function Source({ tile, className, title, onClick, children }: { tile: ReactNode; className: string; title: string; onClick: () => void; children: ReactNode }) {
  return (
    <button className="source" onClick={onClick}>
      <span className={`tile ${className}`}>{tile}</span>
      <span className="source-text">
        <strong>{title}</strong>
        <small>{children}</small>
      </span>
    </button>
  )
}
