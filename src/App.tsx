import { useEffect, useState } from 'react'
import { AddSongSheet } from './components/AddSongSheet'
import { AskHost, ContextMenuHost, isAsking } from './components/Ask'
import { Library } from './components/Library'
import { MiniPlayer } from './components/MiniPlayer'
import { PlayerView } from './components/PlayerView'
import { ChordLibrary } from './components/ChordLibrary'
import { CirclePage } from './components/CirclePage'
import { Keys } from './components/Keys'
import { Transpose, addTransposeFiles } from './components/Transpose'
import { Profile } from './components/Profile'
import { Sidebar } from './components/Sidebar'
import { type MenuCommand, desktop } from './platform'
import { checkForUpdates, startUpdateChecks } from './platform/updates'
import { playback } from './playback'
import {
  addFiles,
  addPaths,
  applyRoute,
  getState,
  loadCapabilities,
  navigate,
  refreshLibrary,
  setState,
  toast,
  useApp,
} from './store'

/** Commands from the native menus and the keyboard. */
function run(cmd: MenuCommand) {
  const s = getState()
  const hasSong = !!playback.state.song
  switch (cmd) {
    case 'add-song':
      return setState({ addOpen: true })
    case 'import-file':
      if (desktop) void desktop.pickFiles('file').then(addPaths)
      else setState({ addOpen: true })
      return
    case 'find':
      navigate('library')
      return setState({ focusSearch: s.focusSearch + 1 })
    case 'go-library':
      return navigate('library')
    case 'go-profile':
      return navigate('profile')
    case 'check-updates':
      navigate('profile')
      return void checkForUpdates()
    case 'save-copy':
      navigate('profile')
      return void window.setTimeout(() => document.querySelector<HTMLElement>('#save-copy')?.scrollIntoView({ behavior: 'smooth' }), 50)
  }
  if (!hasSong) return
  switch (cmd) {
    case 'toggle-play':
      return playback.toggle()
    case 'seek-back':
      return playback.seek(playback.time() - 5)
    case 'seek-forward':
      return playback.seek(playback.time() + 5)
    case 'pitch-up':
      return void playback.setPitch(playback.state.semitones + 1)
    case 'pitch-down':
      return void playback.setPitch(playback.state.semitones - 1)
    case 'speed-up':
      return playback.setSpeed(playback.state.speed + 0.05)
    case 'speed-down':
      return playback.setSpeed(playback.state.speed - 0.05)
    case 'loop':
      return playback.toggleLoop()
    case 'metronome':
      return playback.setMetronome(!playback.state.metronome)
    case 'export':
      navigate('player', playback.state.song!.id)
      return void document.querySelector<HTMLButtonElement>('.controls .pill-btn.accent')?.focus()
  }
}

const KEYS: Record<string, MenuCommand> = {
  ' ': 'toggle-play',
  ArrowLeft: 'seek-back',
  ArrowRight: 'seek-forward',
  ']': 'pitch-up',
  '[': 'pitch-down',
  l: 'loop',
  L: 'loop',
  m: 'metronome',
  M: 'metronome',
}

export function App() {
  const view = useApp((s) => s.view)
  const songId = useApp((s) => s.songId)
  const addOpen = useApp((s) => s.addOpen)
  const sidebar = useApp((s) => s.settings.sidebar)
  const toastState = useApp((s) => s.toast)
  const engine = useApp((s) => s.engine)
  const [dragging, setDragging] = useState(false)

  // A new page opens at its top, not at the last page's scroll position.
  useEffect(() => {
    document.querySelector('.main')?.scrollTo(0, 0)
  }, [view, songId])

  useEffect(() => {
    applyRoute()
    window.addEventListener('hashchange', applyRoute)
    void loadCapabilities()
    void refreshLibrary()
    const stops: (() => void)[] = [() => window.removeEventListener('hashchange', applyRoute)]
    if (desktop) {
      void desktop.engine.info().then((engine) => setState({ engine }))
      stops.push(
        desktop.engine.onStatus((engine) => {
          setState({ engine })
          if (engine.status === 'ready') {
            void loadCapabilities()
            void refreshLibrary()
          }
        }),
        desktop.onMenu(run),
        desktop.onOpenFiles((paths) => void addPaths(paths)),
        startUpdateChecks(),
      )
    }
    let lastError: string | null = null
    stops.push(
      playback.subscribe(() => {
        const { error } = playback.state
        if (error && error !== lastError) toast(error, true)
        lastError = error
      }),
    )
    return () => stops.forEach((s) => s())
  }, [])

  // Single-key shortcuts, kept away from text fields and open dialogs.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || isAsking() || getState().addOpen) return
      const target = e.target as HTMLElement
      if (target.closest('input, textarea, select, [contenteditable]') && !(e.key === ' ' && (target as HTMLInputElement).type === 'range')) return
      if (e.key === ' ' && target.closest('button')) return
      const cmd = KEYS[e.key]
      if (!cmd) return
      e.preventDefault()
      run(cmd)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Drop songs anywhere on the window.
  useEffect(() => {
    let depth = 0
    const hasFiles = (e: DragEvent) => !!e.dataTransfer?.types.includes('Files')
    const enter = (e: DragEvent) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      depth++
      setDragging(true)
    }
    const over = (e: DragEvent) => {
      if (hasFiles(e)) e.preventDefault()
    }
    const leave = () => {
      depth = Math.max(0, depth - 1)
      if (!depth) setDragging(false)
    }
    const drop = (e: DragEvent) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      depth = 0
      setDragging(false)
      const files = [...(e.dataTransfer?.files ?? [])]
      // On the Transpose page, dropped files are for transposing; anywhere else they're songs.
      void (location.hash === '#/transpose' ? addTransposeFiles(files) : addFiles(files))
    }
    window.addEventListener('dragenter', enter)
    window.addEventListener('dragover', over)
    window.addEventListener('dragleave', leave)
    window.addEventListener('drop', drop)
    return () => {
      window.removeEventListener('dragenter', enter)
      window.removeEventListener('dragover', over)
      window.removeEventListener('dragleave', leave)
      window.removeEventListener('drop', drop)
    }
  }, [])

  return (
    <div className={`app ${sidebar ? '' : 'sidebar-hidden'} ${desktop ? `desktop ${desktop.platform}` : 'web'}`}>
      <Sidebar />
      <div className="main">
        {engine && engine.status !== 'ready' && (
          <div className={`banner ${engine.status === 'failed' ? 'error' : ''}`}>
            {engine.status === 'failed' ? (
              <>
                The analysis engine stopped.{' '}
                <button className="text-btn" onClick={() => void desktop?.engine.restart()}>
                  Restart it
                </button>{' '}
                or see Profile for details.
              </>
            ) : engine.status === 'restarting' ? (
              'Restarting the analysis engine…'
            ) : (
              'Starting the analysis engine…'
            )}
          </div>
        )}
        {view === 'library' && <Library />}
        {view === 'profile' && <Profile />}
        {view === 'chords' && <ChordLibrary />}
        {view === 'keys' && <Keys />}
        {view === 'circle' && <CirclePage />}
        {view === 'transpose' && <Transpose />}
        {view === 'player' && songId && <PlayerView songId={songId} />}
      </div>
      {view !== 'player' && <MiniPlayer />}
      {addOpen && <AddSongSheet />}
      {dragging && (
        <div className="drop-overlay">
          <div>Drop to add to your library</div>
        </div>
      )}
      {toastState && (
        <div key={toastState.id} className={`toast ${toastState.error ? 'error' : ''}`} role="status">
          {toastState.message}
        </div>
      )}
      <AskHost />
      <ContextMenuHost />
    </div>
  )
}
