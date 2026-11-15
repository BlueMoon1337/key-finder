// A guitar chord diagram as charts draw it: strings upright, low E on the left, the nut at the
// top (or the fret the shape starts at, beside it), x over a string not played and o over an
// open one, a dot with its finger number on each fretted string, and a bar for a barre.

import { mod12 } from '../music'
import { TUNING, type Voicing } from '../guitar'

const FRETS = 5

export function ChordDiagram({ voicing, rootPc, height = 150, className = '' }: {
  voicing: Voicing
  /** The chord's root, whose dots are drawn darker. */
  rootPc?: number
  height?: number
  className?: string
}) {
  const gap = 16 // between strings
  const row = 18 // between frets
  const left = 22
  const top = 22
  const width = left + gap * 5 + 14
  const total = top + row * FRETS + 8
  // From the nut whenever the shape fits in the first frets (open strings belong there too).
  const first = Math.max(...voicing.frets) <= FRETS ? 1 : voicing.base
  const y = (fret: number) => top + (fret - first + 0.5) * row
  const x = (s: number) => left + s * gap
  return (
    <svg className={`chord-diagram ${className}`} viewBox={`0 0 ${width} ${total}`} height={height} role="img"
      aria-label={`Guitar: ${voicing.frets.map((f) => (f < 0 ? 'x' : f)).join(' ')}`}>
      {/* the nut, or where the shape starts */}
      {first === 1 ? (
        <rect x={left - 1} y={top - 4} width={gap * 5 + 2} height={4} className="nut" />
      ) : (
        <text x={left - 7} y={y(first) + 4} className="fret-number">
          {first}
        </text>
      )}
      {Array.from({ length: FRETS + 1 }, (_, i) => (
        <line key={`f${i}`} x1={left} x2={left + gap * 5} y1={top + i * row} y2={top + i * row} className="fret" />
      ))}
      {Array.from({ length: 6 }, (_, s) => (
        <line key={`s${s}`} x1={x(s)} x2={x(s)} y1={top} y2={top + row * FRETS} className="string" />
      ))}
      {voicing.frets.map((f, s) =>
        f < 0 ? (
          <text key={`m${s}`} x={x(s)} y={top - 9} className="mark">
            ×
          </text>
        ) : f === 0 ? (
          <circle key={`o${s}`} cx={x(s)} cy={top - 12} r={4} className="open" />
        ) : null,
      )}
      {voicing.barre && (
        <rect
          x={x(voicing.barre.from) - 6}
          y={y(voicing.barre.fret) - 6}
          width={x(voicing.barre.to) - x(voicing.barre.from) + 12}
          height={12}
          rx={6}
          className="barre"
        />
      )}
      {voicing.frets.map((f, s) => {
        if (f <= 0) return null
        const root = rootPc !== undefined && mod12(TUNING[s] + f) === mod12(rootPc)
        const inBarre = voicing.barre && f === voicing.barre.fret && s >= voicing.barre.from
        return (
          <g key={`d${s}`}>
            {!inBarre && <circle cx={x(s)} cy={y(f)} r={6.5} className={`dot ${root ? 'root' : ''}`} />}
            {(!inBarre || s === voicing.barre!.from) && voicing.fingers[s] > 0 && (
              <text x={x(s)} y={y(f) + 3.5} className="finger">
                {voicing.fingers[s]}
              </text>
            )}
          </g>
        )
      })}
    </svg>
  )
}
