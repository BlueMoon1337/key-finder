import { useEffect, useMemo, useRef, useState } from 'react'
import { type SongSummary, coverUrl, saveFromApi, stemPath } from '../api'
import { formatTime, keySortValue } from '../music'
import { desktop, isMac } from '../platform'
import { playback } from '../playback'
import {
  type Filter,
  type SortKey,
  errorMessage,
  navigate,
  removeSong,
  renameSong,
  setState,
  toast,
  updateSettings,
  useApp,
} from '../store'
import { type MenuEntry, confirmDialog, showContextMenu } from './Ask'
import { ArrowDownIcon, DotsIcon, FilterIcon, LibraryIcon, PlusIcon, SearchIcon } from './Icons'
import { Sheet } from './Sheet'
import { usePlayback } from './usePlayback'

const SORTS: { key: SortKey; label: string }[] = [
  { key: 'added', label: 'Added' },
  { key: 'title', label: 'Title' },
  { key: 'artist', label: 'Artist' },
  { key: 'bpm', label: 'BPM' },
  { key: 'key', label: 'Key' },
]

const FILTERS: { key: Filter; label: string; test: (s: SongSummary) => boolean }[] = [
  { key: 'all', label: 'All', test: () => true },
  { key: 'ready', label: 'Ready', test: (s) => s.status === 'ready' },
  { key: 'processing', label: 'Processing', test: (s) => s.status === 'queued' || s.status === 'processing' },
  { key: 'major', label: 'Major keys', test: (s) => !!s.key?.endsWith('major') },
  { key: 'minor', label: 'Minor keys', test: (s) => !!s.key?.endsWith('minor') },
]

function compare(a: SongSummary, b: SongSummary, key: SortKey) {
  switch (key) {
    case 'title':
      return a.title.localeCompare(b.title, undefined, { sensitivity: 'base' })
    case 'artist':
      return (a.artist || '￿').localeCompare(b.artist || '￿', undefined, { sensitivity: 'base' })
    case 'bpm':
      return (a.bpm ?? 1e9) - (b.bpm ?? 1e9)
    case 'key':
      return keySortValue(a.key) - keySortValue(b.key)
    default:
      return a.created_at - b.created_at
  }
}

/** Opens a menu under a button, like a native pop-up. */
function menuBelow(el: HTMLElement, items: MenuEntry[]) {
  const r = el.getBoundingClientRect()
  showContextMenu({ clientX: r.left, clientY: r.bottom + 6, preventDefault() {} }, items)
}

export function Library() {
  const songs = useApp((s) => s.songs)
  const libraryError = useApp((s) => s.libraryError)
  const { sort, sortDesc } = useApp((s) => s.settings)
  const focusSearch = useApp((s) => s.focusSearch)
  const engine = useApp((s) => s.engine)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const [editing, setEditing] = useState<SongSummary | null>(null)
  const search = useRef<HTMLInputElement>(null)
  const current = usePlayback((p) => p.song?.id ?? null)

  useEffect(() => {
    if (focusSearch) search.current?.focus()
  }, [focusSearch])

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    const test = FILTERS.find((f) => f.key === filter)!.test
    const list = (songs ?? []).filter(
      (s) => test(s) && (!q || `${s.title} ${s.artist} ${s.key ?? ''}`.toLowerCase().includes(q)),
    )
    list.sort((a, b) => compare(a, b, sort) || a.created_at - b.created_at)
    return sortDesc ? list.reverse() : list
  }, [songs, query, filter, sort, sortDesc])

  const count = (songs ?? []).filter(FILTERS.find((f) => f.key === filter)!.test).length
  const filterLabel = FILTERS.find((f) => f.key === filter)!.label

  const open = (s: SongSummary) => {
    if (s.status === 'ready') navigate('player', s.id)
    else if (s.status === 'error') toast(s.error ?? 'This song couldn’t be processed.', true)
    else toast('Still working on this song…')
  }

  const rowMenu = (s: SongSummary): MenuEntry[] => [
    { label: 'Open', disabled: s.status !== 'ready', onClick: () => open(s) },
    { label: 'Edit Info…', onClick: () => setEditing(s) },
    {
      label: 'Download Original…',
      disabled: s.status !== 'ready',
      onClick: () => void saveFromApi(`${stemPath(s.id, 'original')}?download=true`, `${s.title}.mp3`).catch((e) => toast(errorMessage(e), true)),
    },
    ...(desktop
      ? [{ label: isMac ? 'Show in Finder' : 'Show in Explorer', onClick: () => void desktop!.reveal(s.id) } as MenuEntry]
      : []),
    'separator',
    {
      label: 'Delete…',
      danger: true,
      onClick: async () => {
        const ok = await confirmDialog({
          title: `Delete “${s.title}”?`,
          message: 'Its stems and analysis will be deleted from your library.',
          confirmLabel: 'Delete',
          danger: true,
        })
        if (!ok) return
        if (playback.state.song?.id === s.id) playback.unload()
        try {
          await removeSong(s.id)
        } catch (e) {
          toast(errorMessage(e), true)
        }
      },
    },
  ]

  return (
    <main className="page library">
      <h1 className="page-title">Play</h1>
      <div className="toolbar">
        <label className="search">
          <SearchIcon />
          <input
            ref={search}
            type="search"
            placeholder="Search your library"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Escape' && (setQuery(''), e.currentTarget.blur())}
          />
        </label>
        <button className="pill-btn" onClick={() => setState({ addOpen: true })}>
          <PlusIcon />
          Add
        </button>
      </div>

      <div className="list-controls">
        <button
          className="text-btn"
          onClick={(e) =>
            menuBelow(
              e.currentTarget,
              FILTERS.map((f) => ({
                label: `${f.key === filter ? '✓ ' : '    '}${f.label}`,
                hint: String((songs ?? []).filter(f.test).length),
                onClick: () => setFilter(f.key),
              })),
            )
          }
        >
          <FilterIcon />
          {filterLabel} ({count})
        </button>
        <button
          className="text-btn"
          onClick={(e) =>
            menuBelow(e.currentTarget, [
              ...SORTS.map((o) => ({
                label: `${o.key === sort ? '✓ ' : '    '}${o.label}`,
                onClick: () => updateSettings({ sort: o.key, sortDesc: o.key === 'added' }),
              })),
              'separator',
              { label: sortDesc ? 'Ascending' : 'Descending', onClick: () => updateSettings({ sortDesc: !sortDesc }) },
            ])
          }
        >
          {SORTS.find((o) => o.key === sort)!.label}
          <ArrowDownIcon className={`sort-arrow ${sortDesc ? '' : 'up'}`} />
        </button>
      </div>

      <div className="song-table" role="table" aria-label="Songs">
        <div className="thead" role="row">
          <span role="columnheader">Title</span>
          <span role="columnheader">Artist</span>
          <span role="columnheader">BPM</span>
          <span role="columnheader">Key</span>
          <span />
        </div>
        <div role="rowgroup">
          {visible.map((s) => (
            <SongRow key={s.id} song={s} current={s.id === current} onOpen={() => open(s)} menu={() => rowMenu(s)} />
          ))}
        </div>
      </div>

      {songs === null && !libraryError && <p className="empty">{engine?.status === 'failed' ? '' : 'Loading your library…'}</p>}
      {libraryError && songs === null && <p className="empty">{libraryError}</p>}
      {songs?.length === 0 && (
        <div className="empty-state">
          <img src="logo.svg" alt="" width={56} height={56} />
          <h2>Your library is empty</h2>
          <p>Add a song to find its key, tempo and chords, and split it into vocals, drums, bass and more.</p>
          <button className="pill-btn accent" onClick={() => setState({ addOpen: true })}>
            <PlusIcon />
            Add a song
          </button>
        </div>
      )}
      {!!songs?.length && !visible.length && <p className="empty">No songs match.</p>}
      {editing && <EditInfo song={editing} onClose={() => setEditing(null)} />}
    </main>
  )
}

function SongRow({ song: s, current, onOpen, menu }: { song: SongSummary; current: boolean; onOpen: () => void; menu: () => MenuEntry[] }) {
  const cover = coverUrl(s)
  const busy = s.status === 'queued' || s.status === 'processing'
  return (
    <div
      className={`song-row ${s.status} ${current ? 'current' : ''}`}
      role="row"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => e.key === 'Enter' && onOpen()}
      onContextMenu={(e) => showContextMenu(e, menu())}
    >
      <span className="cell title" role="cell">
        <span className="art">{cover ? <img src={cover} alt="" loading="lazy" /> : <LibraryIcon />}</span>
        <span className="title-text">
          <span className="name">{s.title}</span>
          {busy && (
            <span className="progress" aria-label={`${Math.round(s.progress * 100)}%`}>
              <i style={{ width: `${Math.max(4, s.progress * 100)}%` }} />
            </span>
          )}
        </span>
      </span>
      <span className="cell muted-cell" role="cell">
        {s.artist || '-'}
      </span>
      {busy ? (
        <span className="cell stage" role="cell">
          {s.stage}…
        </span>
      ) : s.status === 'error' ? (
        <span className="cell error" role="cell" title={s.error ?? ''}>
          Couldn’t process this song
        </span>
      ) : (
        <>
          <span className="cell" role="cell" title={s.tempos ? s.tempos.map((t) => Math.round(t)).join(' → ') : undefined}>
            {s.bpm ? Math.round(s.bpm) : '-'}
            {s.tempos && <span className="key-changes"> +{s.tempos.length - 1}</span>}
          </span>
          <span className="cell" role="cell" title={s.keys ? s.keys.join(' → ') : s.duration ? formatTime(s.duration) : undefined}>
            {s.key ?? '-'}
            {s.keys && <span className="key-changes"> +{s.keys.length - 1}</span>}
          </span>
        </>
      )}
      <span className="cell actions" role="cell">
        <button
          className="icon-btn"
          aria-label={`More for ${s.title}`}
          onClick={(e) => {
            e.stopPropagation()
            menuBelow(e.currentTarget, menu())
          }}
        >
          <DotsIcon />
        </button>
      </span>
    </div>
  )
}

function EditInfo({ song, onClose }: { song: SongSummary; onClose: () => void }) {
  const [title, setTitle] = useState(song.title)
  const [artist, setArtist] = useState(song.artist)
  const [saving, setSaving] = useState(false)
  const save = async () => {
    if (!title.trim()) return
    setSaving(true)
    try {
      await renameSong(song.id, { title: title.trim(), artist: artist.trim() })
      const loaded = playback.state.song
      if (loaded?.id === song.id) playback.refreshSong({ ...loaded, title: title.trim(), artist: artist.trim() })
      onClose()
    } catch (e) {
      toast(errorMessage(e), true)
      setSaving(false)
    }
  }
  return (
    <Sheet title="Edit Info" onClose={onClose} small>
      <form
        className="edit-form"
        onSubmit={(e) => {
          e.preventDefault()
          void save()
        }}
      >
        <label className="field">
          Title
          <input autoFocus value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label className="field">
          Artist
          <input value={artist} maxLength={200} onChange={(e) => setArtist(e.target.value)} />
        </label>
        <div className="sheet-actions">
          <button type="button" className="pill-btn" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="pill-btn accent" disabled={!title.trim() || saving}>
            Save
          </button>
        </div>
      </form>
    </Sheet>
  )
}
