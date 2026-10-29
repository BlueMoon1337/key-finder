import { coverUrl } from '../api'
import { playback } from '../playback'
import { errorMessage, loadSong, navigate, neighbour, toast } from '../store'
import { LibraryIcon, NextIcon, PauseIcon, PlayIcon, PrevIcon } from './Icons'
import { usePlayback } from './usePlayback'

/** The floating pill at the bottom of the library: what's loaded, with play and previous / next. */
export function MiniPlayer() {
  const song = usePlayback((p) => p.song)
  const playing = usePlayback((p) => p.playing || p.countingIn)
  if (!song) return null
  const cover = coverUrl(song)
  const skip = async (step: 1 | -1) => {
    const id = neighbour(song.id, step)
    if (!id || id === song.id) return
    const wasPlaying = playback.state.playing
    try {
      await loadSong(id, { autoplay: wasPlaying })
    } catch (e) {
      toast(errorMessage(e), true)
    }
  }
  const title = song.artist ? `${song.title} - ${song.artist}` : song.title
  return (
    <div className="mini-player" role="region" aria-label="Now playing">
      <button className="mini-art" aria-label="Open player" onClick={() => navigate('player', song.id)}>
        {cover ? <img src={cover} alt="" /> : <LibraryIcon />}
      </button>
      <button className="mini-title" onClick={() => navigate('player', song.id)} title={title}>
        <span className={title.length > 34 ? 'scroll' : ''}>{title}</span>
      </button>
      <button className="icon-btn" aria-label="Previous song" onClick={() => void skip(-1)}>
        <PrevIcon />
      </button>
      <button className="icon-btn mini-play" aria-label={playing ? 'Pause' : 'Play'} onClick={() => playback.toggle()}>
        {playing ? <PauseIcon width={26} height={26} /> : <PlayIcon width={26} height={26} />}
      </button>
      <button className="icon-btn" aria-label="Next song" onClick={() => void skip(1)}>
        <NextIcon />
      </button>
    </div>
  )
}
