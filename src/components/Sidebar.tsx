import { useUpdates } from '../platform/updates'
import { navigate, updateSettings, useApp } from '../store'
import { KeysIcon, LibraryIcon, PersonIcon, PianoIcon, SidebarIcon, TransposeIcon } from './Icons'

export function Sidebar() {
  const view = useApp((s) => s.view)
  const open = useApp((s) => s.settings.sidebar)
  const updates = useUpdates()
  return (
    <aside className={`sidebar ${open ? '' : 'collapsed'}`}>
      <button
        className="icon-btn sidebar-toggle"
        aria-label={open ? 'Hide sidebar' : 'Show sidebar'}
        title={open ? 'Hide sidebar' : 'Show sidebar'}
        onClick={() => updateSettings({ sidebar: !open })}
      >
        <SidebarIcon />
      </button>
      <a
        className="brand"
        href="#/"
        onClick={(e) => {
          e.preventDefault()
          navigate('library')
        }}
      >
        <img src="logo.svg" alt="" width={34} height={34} />
        <span>keyfinder</span>
      </a>
      <nav className="nav">
        <button className={`nav-item ${view === 'library' || view === 'player' ? 'active' : ''}`} onClick={() => navigate('library')} title="Play">
          <LibraryIcon />
          <span>Play</span>
        </button>
        <button className={`nav-item ${view === 'chords' ? 'active' : ''}`} onClick={() => navigate('chords')} title="Chords">
          <PianoIcon />
          <span>Chords</span>
        </button>
        <button className={`nav-item ${view === 'keys' ? 'active' : ''}`} onClick={() => navigate('keys')} title="Keys">
          <KeysIcon />
          <span>Keys</span>
        </button>
        <button className={`nav-item ${view === 'transpose' ? 'active' : ''}`} onClick={() => navigate('transpose')} title="Transpose">
          <TransposeIcon />
          <span>Transpose</span>
        </button>
        <button className={`nav-item ${view === 'profile' ? 'active' : ''}`} onClick={() => navigate('profile')} title="Profile">
          <PersonIcon />
          <span>Profile</span>
          {updates.status === 'available' && <i className="dot" aria-label="Update available" />}
        </button>
      </nav>
    </aside>
  )
}
