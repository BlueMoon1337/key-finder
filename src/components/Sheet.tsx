import { type ReactNode, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { isAsking } from './Ask'
import { CloseIcon } from './Icons'

/** A centred sheet over a dimmed window, closed by its × button, Escape or a click outside. */
export function Sheet({ title, onClose, small, children }: { title: string; onClose: () => void; small?: boolean; children: ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isAsking()) {
        e.stopPropagation()
        onClose()
      }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [onClose])
  return createPortal(
    <div className="sheet-backdrop" onPointerDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`sheet ${small ? 'small' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
        <button className="icon-btn round sheet-close" aria-label="Close" onClick={onClose}>
          <CloseIcon />
        </button>
        <h2 className="sheet-title">{title}</h2>
        {children}
      </div>
    </div>,
    document.body,
  )
}
