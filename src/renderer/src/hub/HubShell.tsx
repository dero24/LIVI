// [hub] Phase 1.7 — the HubShell: the top-level surface the appliance shows.
//
// It draws HubState and nothing else (D7). Fluid from the first commit (§12.1):
// no panel pixels, touch targets in physical units, so it renders correctly at
// both the 600x1024 prototype panel and a large wall display. Palette comes from
// the M11 tokens; the health dot degrades honestly when hubd is unreachable.
//
// States (§12.6):
//   - no hubd yet / unreachable   -> screensaver with a quiet "connecting" note
//   - idle (no phones home)       -> screensaver
//   - one or more phones          -> presence row + landing
import { Box, Typography } from '@mui/material'
import { useCallback } from 'react'
import { HealthDot } from './components/HealthDot'
import { PresenceRow } from './components/PresenceRow'
import { Screensaver } from './components/Screensaver'
import type { HubPhone } from './types'
import { useHubState } from './useHubState'
import { useHubTokens } from './useHubTokens'

function isHome(p: HubPhone): boolean {
  return p.presence.rank >= 2 // present | docked | projecting
}

function greeting(now: Date): string {
  const h = now.getHours()
  if (h < 12) return 'Good morning'
  if (h < 18) return 'Good afternoon'
  return 'Good evening'
}

export function HubShell() {
  const t = useHubTokens()
  const { state, healthy, stale } = useHubState()

  const select = useCallback((phoneId: string) => {
    void window.hub?.intent({ type: 'phone.select', phoneId })
  }, [])

  const phones = state?.phones ?? []
  const homePhones = phones.filter(isHome)
  const connecting = state === null || stale

  return (
    <Box
      data-testid="hub-shell"
      sx={{
        position: 'relative',
        width: '100%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: t.bg,
        color: t.text,
        overflow: 'hidden'
      }}
    >
      {/* Health dot, always visible, top-right, out of the way. */}
      <Box sx={{ position: 'absolute', top: '0.6rem', right: '0.6rem', zIndex: 2 }}>
        <HealthDot healthy={healthy} stale={stale} />
      </Box>

      {phones.length === 0 ? (
        <Screensaver message={connecting ? 'Connecting to the hub…' : 'Dock a phone to begin'} />
      ) : (
        <>
          <PresenceRow phones={phones} onSelect={select} />
          <Box
            sx={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.75rem',
              padding: '1rem',
              textAlign: 'center'
            }}
          >
            <Typography sx={{ fontSize: 'clamp(1.5rem, 6vmin, 3rem)', fontWeight: 300 }}>
              {greeting(new Date())}
            </Typography>
            <Typography sx={{ color: t.textMuted, fontSize: 'clamp(0.9rem, 3vmin, 1.4rem)' }}>
              {homePhones.length === 0
                ? 'Nobody is home right now'
                : homePhones.length === phones.length
                  ? 'Everyone is home'
                  : `${homePhones.length} of ${phones.length} home`}
            </Typography>
          </Box>
        </>
      )}
    </Box>
  )
}
