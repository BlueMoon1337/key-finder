// The circle of fifths: the twelve major keys a fifth apart, C at the top and a sharp more each
// step clockwise (a flat more each step anticlockwise), with how many sharps or flats each has
// inside the circle and its key signature on a staff outside. At the bottom the sharp and flat
// keys meet: B is C♭, F♯ is G♭, D♭ is C♯. Coloured round the wheel from yellow C.

import { playChord, typeById, voicing } from '../chords'
import { pcOf } from '../keys'

interface Spot {
  /** The keys at this place on the circle: the usual one first, then its enharmonic twin. */
  keys: { tonic: string; sharps: number; flats: number }[]
  color: string
}

const k = (tonic: string, sharps: number, flats: number) => ({ tonic, sharps, flats })

/** Clockwise from the top. */
export const CIRCLE: Spot[] = [
  { keys: [k('C', 0, 0)], color: '#ffe11c' },
  { keys: [k('G', 1, 0)], color: '#fdb813' },
  { keys: [k('D', 2, 0)], color: '#f7941d' },
  { keys: [k('A', 3, 0)], color: '#f15a2b' },
  { keys: [k('E', 4, 0)], color: '#ec1f5e' },
  { keys: [k('B', 5, 0), k('C♭', 0, 7)], color: '#c9258c' },
  { keys: [k('G♭', 0, 6), k('F♯', 6, 0)], color: '#7e3f98' },
  { keys: [k('D♭', 0, 5), k('C♯', 7, 0)], color: '#2e5eaa' },
  { keys: [k('A♭', 0, 4)], color: '#17aebd' },
  { keys: [k('E♭', 0, 3)], color: '#1faa6a' },
  { keys: [k('B♭', 0, 2)], color: '#3cb64b' },
  { keys: [k('F', 0, 1)], color: '#9aca3c' },
]

/** Dark text on the light colours, white on the dark ones. */
function inkFor(hex: string) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.04 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.2 ? '#141414' : '#ffffff'
}

// ------------------------------------------------------------------ staff

// A staff drawn with 8 units between lines: the top line (F) at y 0, the bottom (E) at y 32.
const LINE = 8
/** Where each sharp and flat of a key signature goes, in steps up from the bottom line (E = 0). */
const SHARP_STEPS = [8, 5, 9, 6, 3, 7, 4] // F C G D A E B
const FLAT_STEPS = [4, 7, 3, 6, 2, 5, 1] // B E A D G C F
const stepY = (step: number) => 32 - step * (LINE / 2)

const CLEF =
  'M11.5 24.5C8 25 6.2 22 7.8 19.6C10 16.5 16 17.5 16.2 22.6C16.4 27.6 11.5 30.5 7 29.4C2 28.1 0.2 21.8 3.6 16.8' +
  'C6 13.2 10.6 10.4 12.6 6C14.4 2 13.6 -3.4 11.6 -4.6C9.2 -6 7.6 -1.6 8 2.6L12.2 37C12.6 40.6 10.6 42.6 8.2 42.2C6.2 41.8 5.6 39.4 7.4 38.2'

function Sharp({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x} ${y})`} className="acc">
      <path d="M-1.6 -7.5V7M1.6 -8.5V6" strokeWidth={1.1} />
      <path d="M-3.8 -1.6L3.8 -3.6M-3.8 3.6L3.8 1.6" strokeWidth={2} />
    </g>
  )
}

function Flat({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x} ${y})`} className="acc">
      <path d="M-2.2 -11V4" strokeWidth={1.2} />
      <path d="M-2.2 4C1.5 1.5 4.6 -1.2 3.4 -3C2.2 -4.6 -0.6 -3 -2.2 -1.2" strokeWidth={1.6} fill="none" />
    </g>
  )
}

/** A key signature on a treble staff: ``count`` sharps or flats. Returns it and its width. */
export function staffWidth(count: number) {
  return 26 + count * 9 + 6
}

export function KeySignature({ sharps, flats }: { sharps: number; flats: number }) {
  const count = sharps || flats
  const width = staffWidth(count)
  return (
    <g className="key-signature">
      {[0, 1, 2, 3, 4].map((i) => (
        <line key={i} x1={0} x2={width} y1={i * LINE} y2={i * LINE} className="staff-line" />
      ))}
      <path d={CLEF} className="clef" transform="translate(3 0)" />
      {Array.from({ length: count }, (_, i) =>
        sharps ? <Sharp key={i} x={28 + i * 9} y={stepY(SHARP_STEPS[i])} /> : <Flat key={i} x={28 + i * 9} y={stepY(FLAT_STEPS[i])} />,
      )}
    </g>
  )
}

// ------------------------------------------------------------------ circle

const R_IN = 148
const R_OUT = 236
const R_COUNT = 122
const R_STAFF = 324
const STAFF_SCALE = 1.15
const TWIN_GAP = 86 // a second staff sits this far below the first

const polar = (r: number, deg: number) => [r * Math.cos((deg * Math.PI) / 180), r * Math.sin((deg * Math.PI) / 180)] as const
const angleOf = (i: number) => -90 + i * 30

function wedge(i: number, grow = 0) {
  const a0 = angleOf(i) - 15
  const a1 = angleOf(i) + 15
  const [x0, y0] = polar(R_OUT + grow, a0)
  const [x1, y1] = polar(R_OUT + grow, a1)
  const [x2, y2] = polar(R_IN, a1)
  const [x3, y3] = polar(R_IN, a0)
  return `M${x0} ${y0}A${R_OUT + grow} ${R_OUT + grow} 0 0 1 ${x1} ${y1}L${x2} ${y2}A${R_IN} ${R_IN} 0 0 0 ${x3} ${y3}Z`
}

const sup = (n: number, sharp: boolean) => `${n}${sharp ? '♯' : '♭'}`

/**
 * The circle of fifths. ``picked`` is the major key whose signature is showing (a minor key's
 * relative major); clicking a key, its name or its staff picks it and plays its chord.
 */
export function CircleOfFifths({ picked, onPick }: { picked: string | null; onPick: (tonic: string) => void }) {
  const pickedPc = picked ? pcOf(picked) : null
  const pick = (tonic: string) => {
    onPick(tonic)
    playChord(voicing(pcOf(tonic), typeById('maj')!))
  }
  const keyProps = (tonic: string, label: string) => ({
    role: 'button',
    tabIndex: 0,
    'aria-label': label,
    onClick: (e: React.MouseEvent) => {
      e.stopPropagation()
      pick(tonic)
    },
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        pick(tonic)
      }
    },
  })

  return (
    <svg className="circle-of-fifths" viewBox="-410 -380 820 860" role="group" aria-label="Circle of fifths">
      {CIRCLE.map((spot, i) => {
        const [main, twin] = spot.keys
        const on = pickedPc !== null && pcOf(main.tonic) === pickedPc
        const ink = inkFor(spot.color)
        const [tx, ty] = polar((R_IN + R_OUT) / 2, angleOf(i))
        const name = (tonic: string) => `${tonic} major`
        return (
          <g key={main.tonic} className={`cof-spot ${on ? 'on' : ''}`}>
            <path d={wedge(i, on ? 10 : 0)} fill={spot.color} className="cof-wedge" {...keyProps(main.tonic, name(main.tonic))} />
            {twin ? (
              <text x={tx} y={ty - 14} className="cof-name pair" fill={ink}>
                <tspan className={picked === main.tonic ? 'picked' : ''} {...keyProps(main.tonic, name(main.tonic))}>
                  {main.tonic}
                </tspan>
                <tspan x={tx} dy={30} className={`twin ${picked === twin.tonic ? 'picked' : ''}`} {...keyProps(twin.tonic, name(twin.tonic))}>
                  {twin.tonic}
                </tspan>
              </text>
            ) : (
              <text x={tx} y={ty} className="cof-name" fill={ink} pointerEvents="none">
                {main.tonic}
              </text>
            )}
            {/* how many sharps or flats, just inside the circle */}
            {(() => {
              const [cx, cy] = polar(R_COUNT - (twin ? 6 : 0), angleOf(i))
              const counts = spot.keys.filter((x) => x.sharps || x.flats).map((x) => sup(x.sharps || x.flats, !!x.sharps))
              return counts.length === 2 ? (
                <text x={cx} y={cy - 9} className="cof-count">
                  <tspan x={cx}>{counts[0]}</tspan>
                  <tspan x={cx} dy={20}>
                    {counts[1]}
                  </tspan>
                </text>
              ) : (
                <text x={cx} y={cy} className="cof-count">
                  {counts[0] ?? ''}
                </text>
              )
            })()}
            {/* the key signature outside, two at the bottom where sharps and flats meet */}
            {spot.keys.map((key, j) => {
              const count = key.sharps || key.flats
              const w = staffWidth(count) * STAFF_SCALE
              const h = 32 * STAFF_SCALE
              const [sx, sy] = polar(R_STAFF, angleOf(i))
              const x = sx - w / 2
              const y = sy - h / 2 + j * TWIN_GAP
              const signatureOf = picked === key.tonic
              return (
                <g
                  key={key.tonic}
                  className={`cof-staff ${signatureOf ? 'on' : ''}`}
                  transform={`translate(${x} ${y}) scale(${STAFF_SCALE})`}
                  {...keyProps(key.tonic, `${key.tonic} major: ${count ? `${count} ${key.sharps ? 'sharp' : 'flat'}${count > 1 ? 's' : ''}` : 'no sharps or flats'}`)}
                >
                  <rect x={-8} y={-16} width={staffWidth(count) + 16} height={68} rx={8} className="cof-staff-card" />
                  <KeySignature sharps={key.sharps} flats={key.flats} />
                </g>
              )
            })}
          </g>
        )
      })}
    </svg>
  )
}
