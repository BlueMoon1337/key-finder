import { CircleOfFifths } from './CircleOfFifths'
import { KeyDetail, usePickedKey } from './KeyDetail'

/**
 * The circle of fifths on a page of its own, with the key it has open beside it (the same key the
 * Keys page has open): hover a key to see its sharps or flats, click one to open it and hear it.
 */
export function CirclePage() {
  const { key, choose } = usePickedKey()
  return (
    <main className="page circle-page">
      <h1>Circle of Fifths</h1>
      <div className="circle-page-body">
        <section className="panel circle-panel">
          <p className="hint">
            Each step clockwise is a fifth up and one more sharp; each step anticlockwise, a fourth up and one more flat. The outer ring is
            each major key’s relative minor, with the same signature. Hover a key to see its sharps or flats; click a key, a name or a
            signature to open it and hear it.
          </p>
          <CircleOfFifths picked={{ tonic: key.tonic, mode: key.mode }} onPick={choose} />
        </section>
        <KeyDetail keyInfo={key} onChoose={choose} className="circle-detail" />
      </div>
    </main>
  )
}
