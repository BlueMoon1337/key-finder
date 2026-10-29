import { useEffect, useRef } from 'react'

/** Calls `fn` on every animation frame while the component is mounted. */
export function useFrame(fn: () => void) {
  const ref = useRef(fn)
  ref.current = fn
  useEffect(() => {
    let raf = 0
    const tick = () => {
      ref.current()
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [])
}
