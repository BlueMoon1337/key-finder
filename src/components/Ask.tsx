import { useEffect, useRef, useState, useSyncExternalStore } from 'react'

/**
 * KeyFinder's own confirm and prompt boxes (from Player and Lumen): they look like the app, answer to
 * Return (yes) and Escape (no), and keep keys away from the playback shortcuts while open.
 */

export interface AskOptions {
  title: string
  message?: string
  /** The button that says yes: "Delete", "Rename"… */
  confirmLabel?: string
  /** A red button, for something that throws work away. */
  danger?: boolean
}

export interface PromptOptions extends AskOptions {
  defaultValue?: string
  placeholder?: string
}

interface Pending extends PromptOptions {
  kind: 'confirm' | 'prompt' | 'alert'
  seq: number
  /** The text typed for a prompt, '' for yes to a confirm, null for Cancel. */
  resolve: (answer: string | null) => void
}

let pending: Pending | null = null
let seq = 0
const listeners = new Set<() => void>()
const setPending = (p: Pending | null) => {
  pending = p
  listeners.forEach((fn) => fn())
}

function ask(kind: Pending['kind'], options: PromptOptions): Promise<string | null> {
  return new Promise((resolve) => {
    // A new question cancels one left open.
    pending?.resolve(null)
    setPending({ ...options, kind, seq: ++seq, resolve })
  })
}

/** Asks a yes-or-no question; true for yes. */
export const confirmDialog = (options: AskOptions) => ask('confirm', options).then((a) => a !== null)

/** Tells something, with just OK. */
export const alertDialog = (options: AskOptions) => ask('alert', options).then(() => undefined)

/** A delete asks twice: what goes, then "Are you sure?". */
export async function confirmDelete(options: AskOptions, what: string): Promise<boolean> {
  if (!(await confirmDialog({ confirmLabel: 'Delete', danger: true, ...options }))) return false
  return confirmDialog({ title: 'Are you sure?', message: `${what} will be deleted.`, confirmLabel: 'Delete', danger: true })
}

/** Asks for a line of text; null when cancelled. */
export const promptDialog = (options: PromptOptions) => ask('prompt', options)

/** Whether a question is open (keys belong to it, not to the shortcuts). */
export const isAsking = () => pending !== null

/** Renders the open question. Mount once. */
export function AskHost() {
  const p = useSyncExternalStore(
    (fn) => {
      listeners.add(fn)
      return () => listeners.delete(fn)
    },
    () => pending,
  )
  return p ? <AskBox key={p.seq} ask={p} /> : null
}

function AskBox({ ask }: { ask: Pending }) {
  const [value, setValue] = useState(ask.defaultValue ?? '')
  const confirmRef = useRef<HTMLButtonElement>(null)
  const answer = (a: string | null) => {
    if (pending === ask) setPending(null)
    ask.resolve(a)
  }
  const ok = () => {
    if (ask.kind !== 'prompt') return answer('')
    if (value.trim()) answer(value.trim())
  }

  useEffect(() => {
    if (ask.kind !== 'prompt') confirmRef.current?.focus()
    // Escape and Return answer, wherever the focus is; the window's other keys wait.
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') answer(null)
      else if (e.key === 'Enter' && !e.isComposing) ok()
      else return
      e.preventDefault()
      e.stopImmediatePropagation()
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  })

  return (
    <div className="menu-backdrop center ask-backdrop" onKeyDown={(e) => e.stopPropagation()}>
      <div className="dialog ask" role="alertdialog" aria-modal="true" aria-label={ask.title}>
        <h3 className="ask-title">{ask.title}</h3>
        {ask.message && <p className="ask-message">{ask.message}</p>}
        {ask.kind === 'prompt' && (
          <input
            autoFocus
            value={value}
            placeholder={ask.placeholder}
            onChange={(e) => setValue(e.target.value)}
            onFocus={(e) => e.target.select()}
            aria-label={ask.title}
          />
        )}
        <div className="dialog-actions">
          <span className="dialog-actions-spacer" />
          {ask.kind !== 'alert' && <button onClick={() => answer(null)}>Cancel</button>}
          <button
            ref={confirmRef}
            className={ask.danger ? 'destructive' : 'primary'}
            disabled={ask.kind === 'prompt' && !value.trim()}
            onClick={ok}
          >
            {ask.confirmLabel ?? 'OK'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- context menu

export interface MenuItem {
  label: string
  onClick?: () => void
  disabled?: boolean
  danger?: boolean
  /** Shown greyed on the right, e.g. "⌫". */
  hint?: string
  submenu?: MenuItem[]
}
export type MenuEntry = MenuItem | 'separator'

let openMenu: { x: number; y: number; items: MenuEntry[] } | null = null
const menuListeners = new Set<() => void>()
const setMenu = (m: typeof openMenu) => {
  openMenu = m
  menuListeners.forEach((fn) => fn())
}

/** Opens a right-click menu at the pointer. */
export function showContextMenu(e: { clientX: number; clientY: number; preventDefault(): void }, items: MenuEntry[]) {
  e.preventDefault()
  setMenu({ x: e.clientX, y: e.clientY, items })
}

/** Keeps a submenu on screen: up from the bottom edge, or to the left at the right edge. */
function fitSubmenu(e: React.MouseEvent<HTMLDivElement>) {
  const sub = e.currentTarget.querySelector<HTMLElement>(':scope > .ctx-submenu')
  if (!sub) return
  sub.style.top = ''
  sub.style.left = ''
  sub.style.right = ''
  const r = sub.getBoundingClientRect()
  const over = r.bottom - (window.innerHeight - 4)
  if (over > 0) sub.style.top = `${-5 - Math.min(over, r.top - 4)}px`
  if (r.right > window.innerWidth - 4) {
    sub.style.left = 'auto'
    sub.style.right = '100%'
  }
}

export function ContextMenuHost() {
  const m = useSyncExternalStore(
    (fn) => {
      menuListeners.add(fn)
      return () => menuListeners.delete(fn)
    },
    () => openMenu,
  )
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null)

  useEffect(() => {
    if (!m) return
    // Keep the menu on screen.
    const el = ref.current
    const w = el?.offsetWidth ?? 200
    const h = el?.offsetHeight ?? 200
    setPos({ x: Math.min(m.x, window.innerWidth - w - 4), y: Math.min(m.y, window.innerHeight - h - 4) })
    const close = (e: Event) => {
      if (e instanceof KeyboardEvent && e.key !== 'Escape') return
      if (e.type === 'pointerdown' && ref.current?.contains(e.target as Node)) return
      setMenu(null)
    }
    window.addEventListener('pointerdown', close, true)
    window.addEventListener('keydown', close, true)
    window.addEventListener('blur', close)
    return () => {
      window.removeEventListener('pointerdown', close, true)
      window.removeEventListener('keydown', close, true)
      window.removeEventListener('blur', close)
      setPos(null)
    }
  }, [m])

  if (!m) return null
  const render = (items: MenuEntry[]) =>
    items.map((it, i) =>
      it === 'separator' ? (
        <div key={i} className="ctx-sep" />
      ) : it.submenu ? (
        <div key={i} className={`ctx-item has-sub ${it.disabled ? 'disabled' : ''}`} onMouseEnter={fitSubmenu}>
          <span>{it.label}</span>
          <span className="ctx-hint">▸</span>
          {!it.disabled && <div className="ctx-menu ctx-submenu">{render(it.submenu)}</div>}
        </div>
      ) : (
        <button
          key={i}
          className={`ctx-item ${it.danger ? 'danger' : ''}`}
          disabled={it.disabled}
          onClick={() => {
            setMenu(null)
            it.onClick?.()
          }}
        >
          <span>{it.label}</span>
          {it.hint && <span className="ctx-hint">{it.hint}</span>}
        </button>
      ),
    )
  return (
    <div
      ref={ref}
      className="ctx-menu"
      role="menu"
      style={{ left: (pos ?? m).x, top: (pos ?? m).y, visibility: pos ? 'visible' : 'hidden' }}
      onContextMenu={(e) => e.preventDefault()}
    >
      {render(m.items)}
    </div>
  )
}
