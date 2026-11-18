// The circle of fifths: the twelve major keys a fifth apart, C at the top and a sharp more each
// step clockwise (a flat more each step anticlockwise), their relative minors in a ring round
// them, how many sharps or flats each has inside the circle, and its key signature on a staff
// outside. At the bottom the sharp and flat keys meet: B is C♭, F♯ is G♭, D♭ is C♯. Coloured round
// the wheel from yellow C. Hovering a key shows its sharps or flats in the middle.

import { useState } from 'react'
import { playChord, typeById, voicing } from '../chords'
import { type Mode, keyInfo, pcOf } from '../keys'

interface Spot {
  /** The major keys at this place on the circle: the usual one first, then its enharmonic twin. */
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

/** A major key's relative minor's tonic: C's is A, C♭'s is A♭. */
export const relativeMinor = (tonic: string) => keyInfo(tonic, 'major').relative.split(' ')[0]
/** The major key whose signature a key uses: its own, or its relative major's. */
const signatureKey = (key: { tonic: string; mode: Mode }) => (key.mode === 'major' ? key.tonic : keyInfo(key.tonic, 'minor').relative.split(' ')[0])

/** The order sharps and flats are added in a key signature. */
const SHARP_ORDER = ['F', 'C', 'G', 'D', 'A', 'E', 'B']
const FLAT_ORDER = ['B', 'E', 'A', 'D', 'G', 'C', 'F']
/** The notes a key sharpens or flattens: D major's are F♯ and C♯. */
export function accidentals(key: { tonic: string; mode: Mode }) {
  const info = keyInfo(key.tonic, key.mode)
  return (info.sharps ? SHARP_ORDER.map((n) => `${n}♯`) : FLAT_ORDER.map((n) => `${n}♭`)).slice(0, info.count)
}

function mix(hex: string, white: number) {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16))
  return `#${c.map((v) => Math.round(v + (255 - v) * white).toString(16).padStart(2, '0')).join('')}`
}

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

/** How wide a key signature of ``count`` sharps or flats is drawn. */
export function staffWidth(count: number) {
  return 26 + count * 9 + 6
}

/** A key signature on a treble staff: ``sharps`` sharps or ``flats`` flats. */
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

const R_HOLE = 132 // the middle, where the counts and the hovered key's sharps or flats go
const R_MAJOR = 222 // the major keys' ring, from R_HOLE
const R_MINOR = 290 // the minor keys' ring, from R_MAJOR
const R_COUNT = 112
const R_STAFF = 374
const STAFF_SCALE = 1.15
const TWIN_GAP = 86 // a second staff sits this far below the first

const polar = (r: number, deg: number) => [r * Math.cos((deg * Math.PI) / 180), r * Math.sin((deg * Math.PI) / 180)] as const
const angleOf = (i: number) => -90 + i * 30

function segment(i: number, r0: number, r1: number) {
  const a0 = angleOf(i) - 15
  const a1 = angleOf(i) + 15
  const [x0, y0] = polar(r1, a0)
  const [x1, y1] = polar(r1, a1)
  const [x2, y2] = polar(r0, a1)
  const [x3, y3] = polar(r0, a0)
  return `M${x0} ${y0}A${r1} ${r1} 0 0 1 ${x1} ${y1}L${x2} ${y2}A${r0} ${r0} 0 0 0 ${x3} ${y3}Z`
}

const sup = (n: number, sharp: boolean) => `${n}${sharp ? '♯' : '♭'}`
const keyName = (key: { tonic: string; mode: Mode }) => `${key.tonic} ${key.mode}`

/**
 * The circle of fifths. ``picked`` is the key open beside it; clicking a key (major or minor),
 * its name or its signature picks it and plays its chord. Hovering one shows its sharps or flats.
 */
export function CircleOfFifths({ picked, onPick }: {
  picked: { tonic: string; mode: Mode }
  onPick: (key: { tonic: string; mode: Mode }) => void
}) {
  const [hovered, setHovered] = useState<{ tonic: string; mode: Mode } | null>(null)
  const shown = hovered ?? picked
  const shownSig = signatureKey(shown)
  const pickedSig = signatureKey(picked)
  const pickedPc = pcOf(picked.tonic)

  const pick = (key: { tonic: string; mode: Mode }) => {
    onPick(key)
    playChord(voicing(pcOf(key.tonic), typeById(key.mode === 'major' ? 'maj' : 'min')!))
  }
  /** What makes a wedge, a name or a staff a key you can hover, click or press Enter on. */
  const keyProps = (key: { tonic: string; mode: Mode }, label = keyName(key)) => ({
    role: 'button',
    tabIndex: 0,
    'aria-label': label,
    // A click picks the key without focusing it (focus is for the keyboard), so no focus box shows.
    onMouseDown: (e: React.MouseEvent) => e.preventDefault(),
    onClick: (e: React.MouseEvent) => {
      e.stopPropagation()
      pick(key)
    },
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        pick(key)
      }
    },
    onMouseEnter: (e: React.MouseEvent) => {
      e.stopPropagation()
      setHovered(key)
    },
    onMouseLeave: () => setHovered(null),
    onFocus: () => setHovered(key),
    onBlur: () => setHovered(null),
  })

  /** A ring's names: one key, or two (the usual spelling over its twin). */
  const names = (i: number, r: number, keys: { tonic: string; mode: Mode }[], ink: string, big: number) => {
    const [tx, ty] = polar(r, angleOf(i))
    const label = (key: { tonic: string; mode: Mode }) => (key.mode === 'minor' ? `${key.tonic}m` : key.tonic)
    if (keys.length === 1) {
      return (
        <text x={tx} y={ty} className="cof-name" fill={ink} fontSize={big} pointerEvents="none">
          {label(keys[0])}
        </text>
      )
    }
    return (
      <text x={tx} y={ty - big * 0.42} className="cof-name pair" fill={ink} fontSize={big * 0.75}>
        {keys.map((key, j) => (
          <tspan
            key={key.tonic}
            x={tx}
            dy={j ? big * 0.92 : 0}
            className={`${j ? 'twin' : ''} ${picked.tonic === key.tonic && picked.mode === key.mode ? 'picked' : ''}`}
            {...keyProps(key)}
          >
            {label(key)}
          </tspan>
        ))}
      </text>
    )
  }

  const list = accidentals(shown)
  const lines = list.length > 4 ? [list.slice(0, 4), list.slice(4)] : [list]

  return (
    <svg className="circle-of-fifths" viewBox="-462 -446 924 990" role="group" aria-label="Circle of fifths" onMouseLeave={() => setHovered(null)}>
      {CIRCLE.map((spot, i) => {
        const majors = spot.keys.map((x) => ({ tonic: x.tonic, mode: 'major' as Mode }))
        const minors = spot.keys.map((x) => ({ tonic: relativeMinor(x.tonic), mode: 'minor' as Mode }))
        const minorColor = mix(spot.color, 0.4)
        const majorOn = picked.mode === 'major' && pcOf(majors[0].tonic) === pickedPc
        const minorOn = picked.mode === 'minor' && pcOf(minors[0].tonic) === pickedPc
        const hoverHere = hovered && signatureKey(hovered) && pcOf(signatureKey(hovered)) === pcOf(majors[0].tonic)
        return (
          <g key={majors[0].tonic} className={`cof-spot ${hoverHere ? 'hover' : ''}`}>
            <path d={segment(i, R_HOLE, R_MAJOR)} fill={spot.color} className={`cof-wedge ${majorOn ? 'on' : ''}`} {...keyProps(majors[0])} />
            {names(i, (R_HOLE + R_MAJOR) / 2, majors, inkFor(spot.color), 32)}
            <path d={segment(i, R_MAJOR, R_MINOR)} fill={minorColor} className={`cof-wedge minor ${minorOn ? 'on' : ''}`} {...keyProps(minors[0])} />
            {names(i, (R_MAJOR + R_MINOR) / 2, minors, inkFor(minorColor), 22)}
            {/* how many sharps or flats, just inside the circle */}
            {(() => {
              const [cx, cy] = polar(R_COUNT - (spot.keys.length > 1 ? 6 : 0), angleOf(i))
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
              const label = `${key.tonic} major and ${relativeMinor(key.tonic)} minor: ${count ? `${count} ${key.sharps ? 'sharp' : 'flat'}${count > 1 ? 's' : ''}` : 'no sharps or flats'}`
              return (
                <g
                  key={key.tonic}
                  className={`cof-staff ${pickedSig === key.tonic ? 'on' : ''} ${shownSig === key.tonic ? 'lit' : ''}`}
                  transform={`translate(${sx - w / 2} ${sy - h / 2 + j * TWIN_GAP}) scale(${STAFF_SCALE})`}
                  {...keyProps({ tonic: key.tonic, mode: 'major' }, label)}
                >
                  <rect x={-8} y={-16} width={staffWidth(count) + 16} height={68} rx={8} className="cof-staff-card" />
                  <KeySignature sharps={key.sharps} flats={key.flats} />
                </g>
              )
            })}
          </g>
        )
      })}
      {/* the open key's outline, over every wedge so none of its edges is hidden */}
      {(() => {
        const i = CIRCLE.findIndex((spot) =>
          pcOf(picked.mode === 'major' ? spot.keys[0].tonic : relativeMinor(spot.keys[0].tonic)) === pickedPc,
        )
        if (i < 0) return null
        const [r0, r1] = picked.mode === 'major' ? [R_HOLE, R_MAJOR] : [R_MAJOR, R_MINOR]
        return <path d={segment(i, r0, r1)} className="cof-outline" pointerEvents="none" />
      })()}
      {/* the middle: the hovered (or open) key's sharps or flats */}
      <g className={`cof-readout ${hovered ? 'hovering' : ''}`} aria-live="polite">
        <text y={-46} className="cof-readout-name">
          {keyName(shown)}
        </text>
        <text y={-22} className="cof-readout-sub">
          {list.length ? `${list.length} ${list[0].endsWith('♯') ? 'sharp' : 'flat'}${list.length > 1 ? 's' : ''}` : 'no sharps or flats'}
        </text>
        {lines.map((line, j) => (
          <text key={j} y={lines.length === 1 ? 14 : 8 + j * 30} className="cof-readout-notes">
            {line.join(' ')}
          </text>
        ))}
      </g>
    </svg>
  )
}
