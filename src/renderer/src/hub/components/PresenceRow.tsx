// [hub] The presence row — the family's state, made visible and calm (§2.3).
// It is a view-area inset, not a z-layer (N4): it measures its own rendered
// height and publishes it as `--hub-view-area-top` (and via onHeight), so the
// projected phone can lay its UI out below the bar at ANY panel size, with no
// hard-coded pixels.
import { Box } from '@mui/material'
import { useEffect, useRef } from 'react'
import type { HubPhone } from '../types'
import { useHubTokens } from '../useHubTokens'
import { PhoneBubble } from './PhoneBubble'

export interface PresenceRowProps {
  phones: HubPhone[]
  onSelect?: (phoneId: string) => void
  onHeight?: (px: number) => void
}

export function PresenceRow({ phones, onSelect, onHeight }: PresenceRowProps) {
  const t = useHubTokens()
  const ref = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const publish = (): void => {
      const h = el.getBoundingClientRect().height
      document.documentElement.style.setProperty('--hub-view-area-top', `${Math.round(h)}px`)
      onHeight?.(Math.round(h))
    }
    publish()
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(publish)
    ro.observe(el)
    return () => ro.disconnect()
  }, [onHeight])

  return (
    <Box
      ref={ref}
      role="list"
      aria-label="Phones at home"
      data-testid="hub-presence-row"
      sx={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 'clamp(0.5rem, 2vw, 1.5rem)',
        padding: 'clamp(0.5rem, 1.5vh, 1rem)',
        backgroundColor: t.surface,
        borderBottom: `1px solid ${t.border}`
      }}
    >
      {phones.map((p) => (
        <PhoneBubble key={p.phoneId} phone={p} onSelect={onSelect} />
      ))}
    </Box>
  )
}
