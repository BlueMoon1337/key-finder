// Line icons drawn for KeyFinder (24×24, currentColor).

import type { SVGProps } from 'react'

type P = SVGProps<SVGSVGElement>

const base = (props: P) => ({
  width: 20,
  height: 20,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
  ...props,
})

export const LibraryIcon = (p: P) => (
  <svg {...base(p)}>
    <path d="M5 4v16M8.5 6h6M8.5 10h11M8.5 14h8M8.5 18h5" />
  </svg>
)
export const PersonIcon = (p: P) => (
  <svg {...base(p)}>
    <circle cx="12" cy="8" r="4" />
    <path d="M4.5 20.5c1.2-3.6 4-5.5 7.5-5.5s6.3 1.9 7.5 5.5" />
  </svg>
)
export const SidebarIcon = (p: P) => (
  <svg {...base(p)}>
    <rect x="3" y="4.5" width="18" height="15" rx="3" />
    <path d="M9.5 4.5v15M5.5 8.5h2M5.5 11.5h2" />
  </svg>
)
export const SearchIcon = (p: P) => (
  <svg {...base({ strokeWidth: 2, ...p })}>
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-3.8-3.8" />
  </svg>
)
export const PlusIcon = (p: P) => (
  <svg {...base({ strokeWidth: 2, ...p })}>
    <path d="M12 4v16M4 12h16" />
  </svg>
)
export const FilterIcon = (p: P) => (
  <svg {...base(p)}>
    <path d="M4 7h16M7 12h10M10 17h4" />
  </svg>
)
export const ArrowDownIcon = (p: P) => (
  <svg {...base({ strokeWidth: 2, ...p })}>
    <path d="M12 4v15M6 13l6 6 6-6" />
  </svg>
)
export const DotsIcon = (p: P) => (
  <svg {...base({ fill: 'currentColor', stroke: 'none', ...p })}>
    <circle cx="5" cy="12" r="1.7" />
    <circle cx="12" cy="12" r="1.7" />
    <circle cx="19" cy="12" r="1.7" />
  </svg>
)
export const PlayIcon = (p: P) => (
  <svg {...base({ fill: 'currentColor', stroke: 'none', ...p })}>
    <path d="M7 4.5v15a1 1 0 0 0 1.5.86l12.5-7.5a1 1 0 0 0 0-1.72L8.5 3.64A1 1 0 0 0 7 4.5Z" />
  </svg>
)
export const PauseIcon = (p: P) => (
  <svg {...base({ fill: 'currentColor', stroke: 'none', ...p })}>
    <rect x="6" y="4" width="4.5" height="16" rx="1.2" />
    <rect x="13.5" y="4" width="4.5" height="16" rx="1.2" />
  </svg>
)
export const PrevIcon = (p: P) => (
  <svg {...base({ fill: 'currentColor', stroke: 'none', ...p })}>
    <path d="M11 6.2v11.6a.8.8 0 0 1-1.25.66L1.6 12.66a.8.8 0 0 1 0-1.32l8.15-5.8A.8.8 0 0 1 11 6.2Zm11 0v11.6a.8.8 0 0 1-1.25.66l-8.15-5.8a.8.8 0 0 1 0-1.32l8.15-5.8A.8.8 0 0 1 22 6.2Z" />
  </svg>
)
export const NextIcon = (p: P) => (
  <svg {...base({ fill: 'currentColor', stroke: 'none', ...p })}>
    <path d="M13 6.2v11.6a.8.8 0 0 0 1.25.66l8.15-5.8a.8.8 0 0 0 0-1.32l-8.15-5.8A.8.8 0 0 0 13 6.2Zm-11 0v11.6a.8.8 0 0 0 1.25.66l8.15-5.8a.8.8 0 0 0 0-1.32l-8.15-5.8A.8.8 0 0 0 2 6.2Z" />
  </svg>
)
export const Back5Icon = (p: P) => (
  <svg {...base(p)}>
    <path d="M4 12a8 8 0 1 0 2.4-5.7M4 4v4h4" />
    <text x="12" y="15.5" fontSize="7.5" fontWeight="700" textAnchor="middle" fill="currentColor" stroke="none">
      5
    </text>
  </svg>
)
export const Forward5Icon = (p: P) => (
  <svg {...base(p)}>
    <path d="M20 12a8 8 0 1 1-2.4-5.7M20 4v4h-4" />
    <text x="12" y="15.5" fontSize="7.5" fontWeight="700" textAnchor="middle" fill="currentColor" stroke="none">
      5
    </text>
  </svg>
)
export const CloseIcon = (p: P) => (
  <svg {...base({ strokeWidth: 2, ...p })}>
    <path d="M6 6l12 12M18 6 6 18" />
  </svg>
)
export const ChevronLeftIcon = (p: P) => (
  <svg {...base({ strokeWidth: 2, ...p })}>
    <path d="m15 5-7 7 7 7" />
  </svg>
)
export const FolderIcon = (p: P) => (
  <svg {...base(p)}>
    <path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2Z" />
  </svg>
)

/** The colourful app-style tiles in the Add a Song sheet. */
export const FilesTile = () => (
  <svg viewBox="0 0 48 48" aria-hidden>
    <path d="M6 14a4 4 0 0 1 4-4h9l4 4h15a4 4 0 0 1 4 4v18a4 4 0 0 1-4 4H10a4 4 0 0 1-4-4Z" fill="#1b8cf2" />
    <path d="M6 19a3 3 0 0 1 3-3h30a3 3 0 0 1 3 3v17a4 4 0 0 1-4 4H10a4 4 0 0 1-4-4Z" fill="#4fb1ff" />
  </svg>
)
const PETALS = ['#fbbf24', '#f97316', '#ef4444', '#d946ef', '#8b5cf6', '#3b82f6', '#14b8a6', '#84cc16']
export const PhotosTile = () => (
  <svg viewBox="0 0 48 48" aria-hidden>
    <g opacity="0.88">
      {PETALS.map((c, i) => (
        <ellipse key={c} cx="24" cy="13" rx="5.5" ry="9" fill={c} transform={`rotate(${i * 45} 24 24)`} />
      ))}
    </g>
  </svg>
)
export const MusicTile = () => (
  <svg viewBox="0 0 48 48" aria-hidden>
    <path d="M19 32.5V14l15-3v17.5" fill="none" stroke="#fff" strokeWidth="3" strokeLinejoin="round" />
    <ellipse cx="15.5" cy="33" rx="4.5" ry="3.6" fill="#fff" />
    <ellipse cx="30.5" cy="29" rx="4.5" ry="3.6" fill="#fff" />
  </svg>
)
export const StemsTile = () => (
  <svg viewBox="0 0 48 48" aria-hidden fill="#fff">
    {[14, 20, 26, 32].map((y, i) => (
      <rect key={y} x={10 + (i % 2) * 4} y={y - 2} width={24 - (i % 2) * 6 + (i === 2 ? 4 : 0)} height="3.6" rx="1.8" />
    ))}
  </svg>
)
export const LinkTile = () => (
  <svg viewBox="0 0 48 48" aria-hidden fill="none" stroke="#fff" strokeWidth="3.2" strokeLinecap="round">
    <path d="M21 27a6 6 0 0 0 8.5 0l6-6a6 6 0 0 0-8.5-8.5l-1.5 1.5" />
    <path d="M27 21a6 6 0 0 0-8.5 0l-6 6a6 6 0 0 0 8.5 8.5l1.5-1.5" />
  </svg>
)
