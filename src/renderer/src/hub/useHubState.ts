// [hub] Subscribe to HubState pushes from hubd (via window.hub) and derive a
// health signal: the shell must visibly degrade if hubd goes away, rather than
// silently freezing on the last state (§7.6 / N6 from the UI's side).
import { useEffect, useState } from 'react'
import type { HubState } from './types'

export interface UseHubStateResult {
  state: HubState | null
  /** hubd is publishing, its bridge to LIVI is up, and state is fresh. */
  healthy: boolean
  /** No state received within `staleAfterMs` (default 30s). */
  stale: boolean
}

export function useHubState(opts?: { staleAfterMs?: number }): UseHubStateResult {
  const staleAfterMs = opts?.staleAfterMs ?? 30_000
  const [state, setState] = useState<HubState | null>(null)
  const [lastAt, setLastAt] = useState(0)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const hub = window.hub
    if (!hub) return
    const apply = (s: HubState): void => {
      setState(s)
      setLastAt(Date.now())
    }
    // Pull the last known state immediately so a fresh mount is not blank...
    hub
      .getState()
      .then((s) => {
        if (s) apply(s)
      })
      .catch(() => {})
    // ...then follow live pushes.
    return hub.onState(apply)
  }, [])

  // Tick so `stale` recomputes even with no new pushes (drives the health dot).
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])

  const stale = lastAt === 0 || now - lastAt > staleAfterMs
  const bridgeUp = state?.health?.bridge !== false
  const healthy = !stale && bridgeUp && state?.health?.ok !== false

  return { state, healthy, stale }
}
