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
import { useCallback, useEffect, useRef, useState } from 'react'
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
  const barRef = useRef<HTMLDivElement | null>(null)
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

  // [hub] Measure the full bar (clock + presence row) and publish as
  // projectionViewAreaTop. Re-runs when phones change (PresenceRow
  // appears/disappears) and when the component mounts.
  useEffect(() => {
    const el = barRef.current
    if (!el) return
    const publish = (): void => {
      const h = el.getBoundingClientRect().height
      if (h > 0) onBarHeight(Math.round(h))
    }
    // Delay slightly so the clock + presence row have rendered
    const id = setTimeout(publish, 50)
    if (typeof ResizeObserver === 'undefined') return () => clearTimeout(id)
    const ro = new ResizeObserver(publish)
    ro.observe(el)
    return () => {
      clearTimeout(id)
      ro.disconnect()
    }
  }, [onBarHeight, phones.length])

  // [hub] §12.2: when a phone is projecting, the HubShell becomes a transparent
  // hole below the presence bar so the native GStreamer video plane (composited
  // behind the Electron window) shows through. The presence bar stays opaque —
  // it is the view-area inset. The video plane is toggled by Projection.tsx
  // (setVisible + show-video class), gated on receivingVideo from LIVI.
  const anyProjecting = phones.some((p) => p.presence.level === 'projecting')

  // [hub] §12.2: when projecting, ALL DOM elements between the HubShell and
  // the projection-root (z-0, fixed) must be transparent to pointer events.
  // The projection-root sits at z-0, but #content-root (position:relative) and
  // its child wrappers paint on top because they come later in DOM order.
  // Without pointer-events:none on these wrappers, touches are captured before
  // reaching the projection-root's videoContainer multi-touch handler.
  //
  // We target #content-root (id in AppLayout) and all ancestor wrappers up to
  // (not including) <body>. A MutationObserver re-applies on DOM mutations
  // because React may re-render wrapper elements, resetting inline styles.
  useEffect(() => {
    const apply = () => {
      // Start from #content-root (the closest wrapper above hub-shell that
      // creates a stacking context with position:relative).
      const contentRoot = document.getElementById('content-root')
      if (!contentRoot) return
      const targets: HTMLElement[] = [contentRoot]
      let el: HTMLElement | null = contentRoot.parentElement
      while (el && el.tagName !== 'BODY') {
        targets.push(el)
        el = el.parentElement
      }
      const val = anyProjecting ? 'none' : ''
      targets.forEach((t) => (t.style.pointerEvents = val))
    }
    // Run immediately
    apply()
    // Re-apply if the DOM mutates (React re-renders may reset inline styles)
    const obs = new MutationObserver(() => apply())
    obs.observe(document.body, { childList: true, subtree: true, attributes: true })
    return () => {
      obs.disconnect()
      // Restore on unmount
      const contentRoot = document.getElementById('content-root')
      if (contentRoot) {
        const targets: HTMLElement[] = [contentRoot]
        let el: HTMLElement | null = contentRoot.parentElement
        while (el && el.tagName !== 'BODY') {
          targets.push(el)
          el = el.parentElement
        }
        targets.forEach((t) => (t.style.pointerEvents = ''))
      }
    }
  }, [anyProjecting])

  return (
    <Box
      data-testid="hub-shell"
      sx={{
        position: 'relative',
        width: '100%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: anyProjecting ? 'transparent' : t.bg,
        color: t.text,
        overflow: 'hidden',
        // [hub] §12.2: transparent to events when projecting so touches pass
        // through to the projection-root (z-0) below. Interactive children
        // below re-enable pointer-events: auto explicitly.
        pointerEvents: anyProjecting ? 'none' : 'auto'
      }}
    >
      {/* Health dot, always visible, top-right, out of the way. */}
      <Box
        sx={{
          position: 'absolute',
          top: '0.6rem',
          right: '0.6rem',
          zIndex: 2,
          pointerEvents: 'auto'
        }}
      >
        <HealthDot healthy={healthy} stale={stale} />
      </Box>

      {phones.length === 0 ? (
        <Screensaver message={connecting ? 'Connecting to the hub…' : 'Dock a phone to begin'} />
      ) : (
        <>
          {/* [hub] §12.6: the bar is a view-area inset. It contains:
              - Clock + date (top line, large)
              - Presence row (phone bubbles)
              - Now-playing placeholder (bottom line)
              The bar's total height is measured and published as
              projectionViewAreaTop so the phone lays out below it. */}
          <Box
            ref={barRef}
            sx={{
              pointerEvents: 'auto',
              backgroundColor: t.surface,
              borderBottom: `1px solid ${t.border}`,
              padding: 'clamp(0.75rem, 2vh, 1.5rem) clamp(1rem, 3vw, 2rem)',
              display: 'flex',
              flexDirection: 'column',
              gap: 'clamp(0.5rem, 1.5vh, 1rem)'
            }}
          >
            {/* Clock + date row */}
            <ClockRow />
            {/* Presence bubbles */}
            <PresenceRow phones={phones} onSelect={select} />
          </Box>
          <Box
            sx={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.75rem',
              padding: '1rem',
              textAlign: 'center',
              // [hub] §12.2: transparent hole — let the video plane show through
              // and let touch events pass to the projection layer below.
              pointerEvents: anyProjecting ? 'none' : 'auto'
            }}
          >
            {!anyProjecting && (
              <>
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
              </>
            )}
          </Box>
        </>
      )}

      {/* [hub] G2 / §6.2: the first-run naming + enrollment chip, shown once
          per unnamed/companion-less phone. Naming is an invitation, not a gate. */}
      {phones.length > 0 && (
        <Box sx={{ pointerEvents: 'auto' }}>
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
        </Box>
      )}

      {/* [hub] Phase 2.3: the ring banner is a z-layer over whatever is on
          screen (§12.2/§12.6 state E). It preempts the screensaver, the landing
          page and projection; the previous surface is restored when it ends. */}
      {ring && (
        <Box sx={{ pointerEvents: 'auto' }}>
          <RingBanner
            ring={ring}
            knownPhoneCount={phones.length}
            onAnswer={(phoneId) => intent({ type: 'ring.answer', phoneId })}
            onDecline={(phoneId) => intent({ type: 'ring.decline', phoneId })}
            onSilence={(phoneId) => intent({ type: 'ring.silence', phoneId })}
            onBringToHub={(phoneId) => intent({ type: 'ring.bringToHub', phoneId })}
          />
        </Box>
      )}
    </Box>
  )
}

// [hub] §12.6: clock + date row for the bar header. Updates every second.
// Large time on the left, date on the right. Fluid sizing (§12.1).
function ClockRow() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  const time = now.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  const date = now.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' })
  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'baseline',
        justifyContent: 'space-between',
        gap: '1rem'
      }}
    >
      <Typography
        sx={{
          fontSize: 'clamp(2.5rem, 10vmin, 5rem)',
          fontWeight: 200,
          lineHeight: 1,
          fontVariantNumeric: 'tabular-nums'
        }}
      >
        {time}
      </Typography>
      <Typography
        sx={{
          fontSize: 'clamp(0.8rem, 2.5vmin, 1.2rem)',
          fontWeight: 300,
          opacity: 0.7,
          textAlign: 'right'
        }}
      >
        {date}
      </Typography>
    </Box>
  )
}
