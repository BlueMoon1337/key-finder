import { useSyncExternalStore } from 'react'
import { type PlaybackState, playback } from '../playback'

/** A piece of the playback state; re-renders only when that piece changes. */
export function usePlayback<T>(select: (s: PlaybackState) => T): T {
  return useSyncExternalStore(playback.subscribe, () => select(playback.state))
}

