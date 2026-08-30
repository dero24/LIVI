// [hub] Phase 5: useNowPlaying — subscribes to projection media events and
// exposes a clean now-playing snapshot for the HubShell.  Reuses the same
// projection-event channel as the full Media page (useMediaState) but is
// trimmed to just the fields the hub surface needs.
//
// Data flow:
//   AA/CP → MediaStore → emitProjectionEvent → window.projection.ipc.onEvent
//   Initial snapshot → window.projection.ipc.readMedia()
//
// Returns null when no media has arrived yet or the payload is the default
// "empty" placeholder (error:true + all dashes).

import { useEffect, useRef, useState } from 'react'
import type { MediaPayload, PersistedSnapshot, UsbEvent, Bridge } from '../components/pages/media/types'
import { mergePayload, payloadFromLiveEvent, clamp } from '../components/pages/media/utils'

const UI_TICK_MS = 250 // progress bar update interval (less aggressive than Media page)

export interface NowPlayingData {
  title: string
  artist: string
  album: string
  appName: string
  artworkUrl: string | null
  isPlaying: boolean
  durationMs: number
  elapsedMs: number
  hasMedia: boolean
}

function isEmptyPayload(snap: PersistedSnapshot | null): boolean {
  if (!snap) return true
  if (snap.payload.error) return true
  const m = snap.payload.media
  if (!m) return true
  // Default placeholder has all dashes
  if (m.MediaSongName === '-' && m.MediaArtistName === '-') return true
  return false
}

function toNowPlaying(snap: PersistedSnapshot | null, liveMs: number): NowPlayingData | null {
  if (isEmptyPayload(snap)) return null
  const m = snap!.payload.media
  const base64 = snap!.payload.base64Image
  const guessedMime = base64?.startsWith('/9j/') ? 'image/jpeg' : 'image/png'
  return {
    title: m?.MediaSongName ?? '',
    artist: m?.MediaArtistName ?? '',
    album: m?.MediaAlbumName ?? '',
    appName: m?.MediaAPPName ?? '',
    artworkUrl: base64 ? `data:${guessedMime};base64,${base64}` : null,
    isPlaying: m?.MediaPlayStatus === 1,
    durationMs: m?.MediaSongDuration ?? 0,
    elapsedMs: liveMs,
    hasMedia: true
  }
}

export function useNowPlaying(active: boolean): NowPlayingData | null {
  const [snap, setSnap] = useState<PersistedSnapshot | null>(null)
  const [livePlayMs, setLivePlayMs] = useState<number>(0)

  const lastTick = useRef<number>(performance.now())
  const lastUiUpdate = useRef<number>(0)
  const livePlayMsRef = useRef<number>(0)
  const hydrated = useRef(false)

  // Subscribe to projection media events
  useEffect(() => {
    if (!active) return

    const handler = (_evt: unknown, ...args: unknown[]) => {
      const ev = (args[0] ?? {}) as UsbEvent
      if (ev?.type === 'media-reset') {
        void (async () => {
          try {
            const next = await window.projection.ipc.readMedia()
            if (next) {
              setSnap(next)
              const t0 = next.payload.media?.MediaSongPlayTime ?? 0
              setLivePlayMs(t0)
              livePlayMsRef.current = t0
              lastTick.current = performance.now()
              lastUiUpdate.current = lastTick.current
            }
          } catch { /* ignore */ }
        })()
        return
      }
      const inc = payloadFromLiveEvent(ev)
      if (!inc) return
      setSnap((prev) => {
        const merged = mergePayload(prev?.payload, inc)
        let nextPlay = merged.media?.MediaSongPlayTime ?? 0
        if (inc.media?.MediaSongPlayTime === undefined) {
          const prevPlay = prev?.payload.media?.MediaSongPlayTime
          if (typeof prevPlay === 'number') nextPlay = prevPlay
        }
        setLivePlayMs(nextPlay)
        livePlayMsRef.current = nextPlay
        lastTick.current = performance.now()
        lastUiUpdate.current = lastTick.current
        return { timestamp: new Date().toISOString(), payload: merged }
      })
    }

    const w = window as unknown as Bridge
    let unsubscribe: (() => void) | undefined
    if (typeof w.projection?.ipc?.onEvent === 'function') {
      const maybe = w.projection.ipc.onEvent(handler)
      if (typeof maybe === 'function') unsubscribe = maybe
    }

    return () => {
      if (typeof unsubscribe === 'function') {
        try { unsubscribe() } catch { /* ignore */ }
      }
    }
  }, [active])

  // Initial hydration
  useEffect(() => {
    if (!active || hydrated.current) return
    let cancelled = false
    ;(async () => {
      try {
        const initial = await window.projection.ipc.readMedia()
        if (!cancelled && initial) {
          hydrated.current = true
          setSnap(initial)
          const t0 = initial.payload.media?.MediaSongPlayTime ?? 0
          setLivePlayMs(t0)
          livePlayMsRef.current = t0
          lastTick.current = performance.now()
          lastUiUpdate.current = lastTick.current
        }
      } catch { /* ignore */ }
    })()
    return () => { cancelled = true }
  }, [active])

  // Progress ticker — advances elapsed time while playing
  useEffect(() => {
    if (!active) return
    const interval = setInterval(() => {
      const m = snap?.payload.media
      if (!m || m.MediaPlayStatus !== 1) return
      const now = performance.now()
      const dt = now - lastTick.current
      lastTick.current = now
      const dur = m.MediaSongDuration ?? 0
      const next = clamp((livePlayMsRef.current ?? 0) + dt, 0, dur)
      livePlayMsRef.current = next
      if (now - lastUiUpdate.current >= UI_TICK_MS) {
        lastUiUpdate.current = now
        setLivePlayMs(next)
      }
    }, UI_TICK_MS)
    return () => clearInterval(interval)
  }, [snap, active])

  return toNowPlaying(snap, livePlayMs)
}
