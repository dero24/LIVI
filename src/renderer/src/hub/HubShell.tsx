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
import { useCallback, useRef } from 'react'
import { FirstRunChip } from './components/FirstRunChip'
import { HealthDot } from './components/HealthDot'
import { PresenceRow } from './components/PresenceRow'
import { RingBanner } from './components/RingBanner'
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

  const intent = useCallback((payload: Record<string, unknown>) => {
    void window.hub?.intent(payload)
  }, [])

  const select = useCallback((phoneId: string) => {
    void window.hub?.intent({ type: 'phone.select', phoneId })
  }, [])

  // [hub] G1: the bar is a view-area inset (§12.2). Measure its rendered height
  // (CSS px = display px in the kiosk renderer) and post it as the AA/CP view-
  // area top inset. ServiceDiscoveryBuilder scales display→tier px. Debounced
  // so a resize storm doesn't spam settings.save.
  const viewAreaTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const onBarHeight = useCallback((px: number) => {
    if (viewAreaTimer.current) clearTimeout(viewAreaTimer.current)
    viewAreaTimer.current = setTimeout(() => {
      void window.hub?.intent({
        type: 'settings.set',
        settings: { projectionViewAreaTop: px }
      })
    }, 150)
  }, [])

  const phones = state?.phones ?? []
  const homePhones = phones.filter(isHome)
  const connecting = state === null || stale
  const ring = state?.ring ?? null

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
          <PresenceRow phones={phones} onSelect={select} onHeight={onBarHeight} />
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

      {/* [hub] G2 / §6.2: the first-run naming + enrollment chip, shown once
          per unnamed/companion-less phone. Naming is an invitation, not a gate. */}
      {phones.length > 0 && (
        <FirstRunChip
          phone={phones[0]}
          onRename={(phoneId, name) => intent({ type: 'phone.rename', phoneId, name })}
          onSetAutoDock={(phoneId, autoDock) =>
            intent({ type: 'phone.policy', phoneId, policy: { autoDock } })
          }
          onEnrolStart={async (phoneId) => {
            await intent({ type: 'phone.enrolStart', phoneId })
          }}
        />
      )}

      {/* [hub] Phase 2.3: the ring banner is a z-layer over whatever is on
          screen (§12.2/§12.6 state E). It preempts the screensaver, the landing
          page and projection; the previous surface is restored when it ends. */}
      {ring && (
        <RingBanner
          ring={ring}
          knownPhoneCount={phones.length}
          onAnswer={(phoneId) => intent({ type: 'ring.answer', phoneId })}
          onDecline={(phoneId) => intent({ type: 'ring.decline', phoneId })}
          onSilence={(phoneId) => intent({ type: 'ring.silence', phoneId })}
          onBringToHub={(phoneId) => intent({ type: 'ring.bringToHub', phoneId })}
        />
      )}
    </Box>
  )
}
