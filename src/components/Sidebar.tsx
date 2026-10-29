import { useUpdates } from '../platform/updates'
import { navigate, updateSettings, useApp } from '../store'
import { LibraryIcon, PersonIcon, SidebarIcon } from './Icons'

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
        <button className={`nav-item ${view !== 'profile' ? 'active' : ''}`} onClick={() => navigate('library')} title="Play">
          <LibraryIcon />
          <span>Play</span>
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
