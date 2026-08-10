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
import {
  Landing,
  CalibrationOverlay,
  LANDING_TILES,
  loadCalibration,
  saveCalibration,
  isCalibrated,
  getCalibration,
  type LandingTile,
  type CalibData
} from './components/Landing'
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

  // [hub] §12.4/§12.6: landing page state. When a phone is projecting, show
  // the landing page (tiles) on top of the AA video. The user taps a tile to
  // enter AA. This is a local state within the projection surface — the
  // SurfaceManager still says 'projection' is active.
  const [viewingLanding, setViewingLanding] = useState(true)
  const [calibrating, setCalibrating] = useState(false)
  const [calibrationStep, setCalibrationStep] = useState(0)
  const [calibrationApp, setCalibrationApp] = useState<string | null>(null)
  const [navigating, setNavigating] = useState(false)
  const projectingPhone = phones.find((p) => p.presence.level === 'projecting') ?? null

  // Reset landing state when phone changes
  useEffect(() => {
    setViewingLanding(true)
    setCalibrating(false)
    setCalibrationStep(0)
  }, [projectingPhone?.phoneId])

  // --- App navigation (invisible, with fade) ---
  const navigateToApp = useCallback(
    (appKey: string, onComplete: () => void) => {
      if (!projectingPhone) {
        onComplete()
        return
      }
      const pos = getCalibration(projectingPhone.phoneId, appKey)
      // 1. Go to AA dashboard
      window.projection.ipc.sendCommand('home')
      // 2. Wait for dashboard to render
      setTimeout(() => {
        if (pos && pos.sequence && pos.sequence.length > 0) {
          // 3. Replay recorded touch sequence
          let i = 0
          const playNext = () => {
            if (i >= pos.sequence.length) {
              setTimeout(onComplete, 500)
              return
            }
            const evt = pos.sequence[i]
            window.projection.ipc.sendTouch(
              evt.x / window.innerWidth,
              evt.y / window.innerHeight,
              evt.action
            )
            i++
            const nextDelay = Math.min(evt.delay, 50)
            setTimeout(playNext, nextDelay)
          }
          playNext()
        } else if (pos && pos.x !== undefined) {
          // Fallback: just tap the recorded position
          window.projection.ipc.sendTouch(pos.x / window.innerWidth, pos.y / window.innerHeight, 14)
          setTimeout(() => {
            window.projection.ipc.sendTouch(pos.x / window.innerWidth, pos.y / window.innerHeight, 16)
            setTimeout(onComplete, 800)
          }, 100)
        } else {
          onComplete()
        }
      }, 800)
    },
    [projectingPhone]
  )

  const handleTileTap = useCallback(
    (tile: LandingTile) => {
      if (!projectingPhone) return
      if (tile.calibratable && !isCalibrated(projectingPhone.phoneId, tile.key)) {
        // Start calibration for this specific app
        setCalibrationApp(tile.key)
        setCalibrationStep(1)
        setCalibrating(true)
        // Show AA dashboard for calibration
        window.projection.ipc.sendCommand('home')
        setTimeout(() => {
          // The calibration overlay will handle the rest
        }, 800)
        return
      }
      // Navigate to the app invisibly, then fade to AA
      setNavigating(true)
      navigateToApp(tile.key, () => {
        setNavigating(false)
        setViewingLanding(false)
      })
    },
    [projectingPhone, navigateToApp]
  )

  const handleFullApps = useCallback(() => {
    window.projection.ipc.sendCommand('home')
    setViewingLanding(false)
  }, [])

  // --- Calibration ---
  const handleCalibrationRecord = useCallback(
    (x: number, y: number, sequence: CalibData['sequence']) => {
      if (!projectingPhone || !calibrationApp) return
      const existing = loadCalibration(projectingPhone.phoneId)
      existing[calibrationApp] = { x, y, sequence }
      saveCalibration(projectingPhone.phoneId, existing)
      // Check if there are more uncalibrated apps to calibrate
      const nextApp = LANDING_TILES.find(
        (t) => t.calibratable && t.key !== calibrationApp && !existing[t.key]
      )
      if (nextApp) {
        // Continue to next app
        setCalibrationApp(nextApp.key)
        setCalibrationStep((s) => s + 1)
        // Go back to dashboard for the next calibration
        window.projection.ipc.sendCommand('home')
      } else {
        // All apps calibrated — return to landing
        setCalibrating(false)
        setCalibrationApp(null)
        setCalibrationStep(0)
      }
    },
    [projectingPhone, calibrationApp]
  )

  const handleCalibrationSkip = useCallback(() => {
    if (!projectingPhone || !calibrationApp) {
      setCalibrating(false)
      setCalibrationApp(null)
      setCalibrationStep(0)
      return
    }
    // Check if there are more uncalibrated apps (excluding the skipped one)
    const existing = loadCalibration(projectingPhone.phoneId)
    const nextApp = LANDING_TILES.find(
      (t) => t.calibratable && t.key !== calibrationApp && !existing[t.key]
    )
    if (nextApp) {
      setCalibrationApp(nextApp.key)
      setCalibrationStep((s) => s + 1)
      window.projection.ipc.sendCommand('home')
    } else {
      setCalibrating(false)
      setCalibrationApp(null)
      setCalibrationStep(0)
    }
  }, [projectingPhone, calibrationApp])

  // [hub] §12.2: when projecting AND viewing AA (not landing), touches must
  // pass through #content-root to reach the projection-root (z-0, fixed)
  // below. We set pointer-events:none on #content-root directly — one-shot,
  // no observer. The HubShell root also has pointer-events:none inline.
  // The bar and interactive children override with pointer-events:auto.
  useEffect(() => {
    const passThrough = anyProjecting && !viewingLanding
    const contentRoot = document.getElementById('content-root')
    if (contentRoot) contentRoot.style.pointerEvents = passThrough ? 'none' : ''
    document.documentElement.classList.toggle('hub-touch-passthrough', passThrough)
    return () => {
      if (contentRoot) contentRoot.style.pointerEvents = ''
      document.documentElement.classList.remove('hub-touch-passthrough')
    }
  }, [anyProjecting, viewingLanding])

  return (
    <Box
      data-testid="hub-shell"
      sx={{
        position: 'relative',
        width: '100%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        // [hub] §12.2: transparent when projecting AND (viewing AA OR calibrating).
        // During calibration, the AA dashboard must be visible through the
        // semi-transparent overlay. During landing, opaque covers the AA video.
        // During AA viewing, transparent so touches pass through to projection-root.
        backgroundColor: anyProjecting && (!viewingLanding || calibrating) ? 'transparent' : t.bg,
        color: t.text,
        overflow: 'hidden',
        // [hub] §12.2: transparent to events when projecting AND (viewing AA
        // OR calibrating) so touches pass through to the projection-root.
        // When viewing the landing page, keep events so tiles are interactive.
        pointerEvents: anyProjecting && !viewingLanding ? 'none' : 'auto'
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
              gap: 'clamp(0.5rem, 1.5vh, 1rem)',
              // [hub] §12.6: min height so AA gets a nearly square area below
              // the bar (~400px on a 1024px panel = 600x624 AA area).
              minHeight: 'clamp(300px, 40vh, 450px)'
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
              pointerEvents: anyProjecting && !viewingLanding ? 'none' : 'auto'
            }}
          >
            {/* [hub] §12.4: landing page overlay when projecting. Shows tiles
                on top of the AA video. Fades out when user enters AA.
                Hidden during calibration so AA dashboard is visible through
                the semi-transparent CalibrationOverlay. */}
            {anyProjecting && viewingLanding && !calibrating && projectingPhone && (
              <Landing
                phone={projectingPhone}
                onTileTap={handleTileTap}
                onFullApps={handleFullApps}
              />
            )}

            {/* Navigation pulse indicator */}
            {navigating && (
              <Box
                sx={{
                  position: 'absolute',
                  top: '50%',
                  left: '50%',
                  transform: 'translate(-50%, -50%)',
                  fontSize: '1.2rem',
                  color: t.textMuted,
                  animation: 'pulse 1s ease-in-out infinite',
                  '@keyframes pulse': {
                    '0%, 100%': { opacity: 1 },
                    '50%': { opacity: 0.5 }
                  }
                }}
              >
                Opening…
              </Box>
            )}

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

      {/* [hub] Home button — floating, top-left of the AA area. Returns from
          AA to the landing page. Only visible when viewing AA (not landing). */}
      {anyProjecting && !viewingLanding && !calibrating && (
        <Box
          onClick={() => setViewingLanding(true)}
          sx={{
            position: 'absolute',
            top: 'clamp(0.5rem, 1.5vh, 1rem)',
            left: 'clamp(0.5rem, 1.5vw, 1rem)',
            zIndex: 10,
            pointerEvents: 'auto',
            width: 'clamp(2.5rem, 8vmin, 3.5rem)',
            height: 'clamp(2.5rem, 8vmin, 3.5rem)',
            borderRadius: '50%',
            backgroundColor: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            color: '#fff',
            fontSize: 'clamp(1.2rem, 4vmin, 1.8rem)',
            transition: 'all 200ms cubic-bezier(0.4, 0, 0.2, 1)',
            '&:hover': {
              backgroundColor: 'rgba(0,0,0,0.7)',
              transform: 'scale(1.05)'
            },
            '&:active': {
              transform: 'scale(0.95)'
            }
          }}
        >
          {/* Home icon (simple house glyph) */}
          {'\u{1F3E0}'}
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

      {/* [hub] Calibration overlay — shown when user taps an uncalibrated tile.
          The AA dashboard is visible through the semi-transparent overlay. */}
      {calibrating && calibrationApp && projectingPhone && (
        <CalibrationOverlay
          appLabel={calibrationApp.charAt(0).toUpperCase() + calibrationApp.slice(1)}
          appIcon={LANDING_TILES.find((t) => t.key === calibrationApp)?.icon ?? '?'}
          step={calibrationStep}
          totalSteps={3}
          onRecord={handleCalibrationRecord}
          onSkip={handleCalibrationSkip}
        />
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
