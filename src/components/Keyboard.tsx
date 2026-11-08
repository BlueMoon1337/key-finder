// A piano keyboard drawn from C, with the chord's keys lit: the bass note (a slash chord's)
// in a second colour, and optionally the note names on the lit keys.

const WHITE = [0, 2, 4, 5, 7, 9, 11]
const BLACK = [1, 3, 6, 8, 10]
// Where each black key sits, in white-key widths from the octave's C.
const BLACK_X: Record<number, number> = { 1: 0.62, 3: 1.72, 6: 3.6, 8: 4.68, 10: 5.76 }

export function Keyboard({ lit, bass, octaves = 2, labels, height = 96, className = '' }: {
  /** Keys to light, in semitones from the keyboard's first C. */
  lit: number[]
  /** A bass key to light in its own colour, an octave below the chord (shown in the first octave). */
  bass?: number
  octaves?: number
  /** Note names to print on the lit keys, in the order of ``lit``. */
  labels?: string[]
  height?: number
  className?: string
}) {
  const w = 20
  const h = 80
  const whites: JSX.Element[] = []
  const blacks: JSX.Element[] = []
  const label = (key: number) => {
    const i = lit.indexOf(key)
    return labels && i >= 0 ? labels[i] : null
  }
  for (let o = 0; o < octaves; o++) {
    WHITE.forEach((pc, i) => {
      const key = o * 12 + pc
      const x = (o * 7 + i) * w
      const on = lit.includes(key)
      const isBass = bass !== undefined && key === bass && !on
      whites.push(
        <g key={`w${key}`}>
          <rect x={x} y={0} width={w} height={h} rx={3} className={`key white ${on ? 'on' : ''} ${isBass ? 'bass' : ''}`} />
          {label(key) && (
            <text x={x + w / 2} y={h - 8} className="key-label">
              {label(key)}
            </text>
          )}
        </g>,
      )
    })
    BLACK.forEach((pc) => {
      const key = o * 12 + pc
      const x = (o * 7 + BLACK_X[pc]) * w
      const on = lit.includes(key)
      const isBass = bass !== undefined && key === bass && !on
      blacks.push(
        <g key={`b${key}`}>
          <rect x={x} y={0} width={w * 0.62} height={h * 0.6} rx={2} className={`key black ${on ? 'on' : ''} ${isBass ? 'bass' : ''}`} />
          {label(key) && (
            <text x={x + (w * 0.62) / 2} y={h * 0.6 - 6} className="key-label small">
              {label(key)}
            </text>
          )}
        </g>,
      )
    })
  }
  const width = octaves * 7 * w
  return (
    <svg className={`keyboard ${className}`} viewBox={`-1 -1 ${width + 2} ${h + 2}`} height={height} role="img" aria-label="Piano keyboard">
      {whites}
      {blacks}
    </svg>
  )
}
