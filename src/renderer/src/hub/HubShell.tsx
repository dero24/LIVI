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
import { Box, IconButton, Typography } from '@mui/material'
import SettingsIcon from '@mui/icons-material/Settings'
import { type ReactNode, useCallback, useEffect, useRef, useState } from 'react'
import { FirstRunChip } from './components/FirstRunChip'
import { HealthDot } from './components/HealthDot'
import {
  Landing,
  CalibrationOverlay,
  LANDING_TILES,
  loadCalibration,
  saveCalibration,
  clearCalibration,
  isCalibrated,
  getCalibration,
  type LandingTile,
  type CalibData
} from './components/Landing'
import { PresenceRow } from './components/PresenceRow'
import { RingBanner } from './components/RingBanner'
import { Screensaver } from './components/Screensaver'
import { SettingsPanel } from './components/SettingsPanel'
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

  // [hub] §12.2: latch `anyProjecting` with hysteresis so a one-frame presence
  // blip from hubd (e.g. a status refresh that momentarily drops `projecting` to
  // `docked`) cannot disable AA-mode touch passthrough. Immediate on, 2s
  // delayed off — long enough to ride out a status-flush flicker, short enough
  // that an actual undock reverts to the landing/screensaver promptly.
  const [projectingStable, setProjectingStable] = useState(anyProjecting)
  useEffect(() => {
    if (anyProjecting) {
      setProjectingStable(true)
      return
    }
    const id = setTimeout(() => setProjectingStable(false), 2000)
    return () => clearTimeout(id)
  }, [anyProjecting])

  // [hub] §12.4/§12.6: landing page state. When a phone is projecting, show
  // the landing page (tiles) on top of the AA video. The user taps a tile to
  // enter AA. This is a local state within the projection surface — the
  // SurfaceManager still says 'projection' is active.
  const [viewingLanding, setViewingLanding] = useState(true)
  const [calibrating, setCalibrating] = useState(false)
  const [calibrationStep, setCalibrationStep] = useState(0)
  const [calibrationApp, setCalibrationApp] = useState<string | null>(null)
  const [navigating, setNavigating] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const projectingPhone = phones.find((p) => p.presence.level === 'projecting') ?? null

  // [hub] §12.4: tapping a phone bubble selects it (asks LIVI to make it the
  // active session) AND, if it is the phone currently projecting, returns to
  // the landing page so the user can pick an app. Tapping a non-projecting
  // phone's bubble tries to select it (LIVI returns 409 if no session); we do
  // not change the local view in that case.
  const handleBubbleSelect = useCallback(
    (phoneId: string) => {
      const isProjecting = phones.find((p) => p.phoneId === phoneId)?.presence.level === 'projecting'
      if (isProjecting) setViewingLanding(true)
      select(phoneId)
    },
    [phones, select]
  )

  // [hub] §12.4: reset landing/calibration state when the projecting phone
  // ACTUALLY changes. The previous version keyed on `projectingPhone?.phoneId`
  // directly, which flickers: a hubd presence refresh can briefly drop
  // `presence.level` from `projecting` to `docked`, making projectingPhone null
  // for one render, then back. That fired this effect twice and cancelled a
  // calibration mid-flow (re-showing the Landing over the AA dashboard). Now we
  // only reset when a DIFFERENT phone starts projecting (tracked via a ref that
  // ignores null blips), and separately reset when projection ends entirely
  // (driven by the latched `projectingStable`).
  const prevProjectingPhoneId = useRef<string | undefined>(undefined)
  useEffect(() => {
    const id = projectingPhone?.phoneId
    if (id && id !== prevProjectingPhoneId.current) {
      setViewingLanding(true)
      setCalibrating(false)
      setCalibrationStep(0)
      prevProjectingPhoneId.current = id
    }
    // When id is undefined (a presence blip or an undock), do NOT clear the
    // ref — the same phone returning must not reset state. Full reset on a
    // real undock is handled by the projectingStable effect below.
  }, [projectingPhone?.phoneId])

  useEffect(() => {
    if (!projectingStable) {
      setViewingLanding(true)
      setCalibrating(false)
      setCalibrationStep(0)
    }
  }, [projectingStable])

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
        // Show the AA dashboard so the user can tap where the app lives. The
        // first 'home' can race with AA session bring-up and be dropped, so
        // retry once after a beat. The shell is transparent during calibration
        // (see root backgroundColor) and the Landing is hidden (`!calibrating`
        // in its render gate), so the dashboard shows through the overlay.
        window.projection.ipc.sendCommand('home')
        setTimeout(() => window.projection.ipc.sendCommand('home'), 600)
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

  const handleForgetCalibration = useCallback(() => {
    if (!projectingPhone) return
    clearCalibration(projectingPhone.phoneId)
    setViewingLanding(true) // re-render landing with uncalibrated tiles
  }, [projectingPhone])

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

  // [hub] §12.2: when viewing AA (not landing), toggle 'hub-aa-mode' on <html>.
  // The CSS in index.html is the single source of truth for the passthrough
  // (#content-root:none, #projection-root/#videoContainer:auto,
  // #hub-shell-root:none with .hub-interactive children re-enabled). We do NOT
  // mutate #content-root's inline style — that was racey: hubd presence
  // flickers toggled it and let #content-root briefly capture touches. The
  // latched `projectingStable` (above) drives this so a one-frame blip cannot
  // drop passthrough mid-touch.
  const aaMode = projectingStable && !viewingLanding
  useEffect(() => {
    document.documentElement.classList.toggle('hub-aa-mode', aaMode)
    return () => {
      document.documentElement.classList.remove('hub-aa-mode')
    }
  }, [aaMode])

  return (
    <Box
      data-testid="hub-shell"
      id="hub-shell-root"
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
        // Uses the latched `projectingStable` so a presence blip cannot flash
        // an opaque background over the video mid-touch.
        backgroundColor: projectingStable && (!viewingLanding || calibrating) ? 'transparent' : t.bg,
        color: t.text,
        overflow: 'hidden'
        // pointer-events is intentionally NOT set here: the CSS rule
        // `html.hub-aa-mode #hub-shell-root { pointer-events: none }` is the
        // single source of truth for AA-mode passthrough, and `.hub-interactive`
        // children re-enable it. Setting it inline would override the CSS
        // (inline > rule) and reintroduce the flicker bug.
      }}
    >
      {/* [hub] Top-right cluster: settings gear + health dot. Both stay
          tappable in AA mode via .hub-interactive. The gear opens the
          settings drawer (§12.5). */}
      <Box
        className="hub-interactive"
        sx={{
          position: 'absolute',
          top: '0.6rem',
          right: '0.6rem',
          zIndex: 3,
          pointerEvents: 'auto',
          display: 'flex',
          alignItems: 'center',
          gap: '0.4rem'
        }}
      >
        <IconButton
          aria-label="Settings"
          data-testid="hub-settings-gear"
          onClick={() => setSettingsOpen(true)}
          size="small"
          sx={{ color: t.text, opacity: 0.85, '&:hover': { opacity: 1, backgroundColor: 'rgba(255,255,255,0.08)' } }}
        >
          <SettingsIcon fontSize="small" />
        </IconButton>
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
            className="hub-interactive"
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
            <PresenceRow phones={phones} onSelect={handleBubbleSelect} />
            {/* [hub] §12.6: media transport — prev / play-pause / next.
                Wired to window.projection.ipc.sendCommand, which maps through
                CommandMapping → BUTTON_KEY.MEDIA_* in AaSession's SendCommand
                handler (src/main/services/projection/driver/aa/AaSession.ts).
                Only shown while a phone is projecting (otherwise no AA session
                to receive the button press). */}
            {anyProjecting && <MediaControls />}
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
              textAlign: 'center'
              // [hub] §12.2: pointer-events handled by the `hub-aa-mode` CSS
              // (none on #hub-shell-root, auto on .hub-interactive). This Box
              // is not interactive in AA mode, so it inherits `none` and lets
              // touches fall through to #projection-root below.
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
                onForgetCalibration={handleForgetCalibration}
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
        <Box className="hub-interactive" sx={{ pointerEvents: 'auto' }}>
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

      {/* [hub] Home button — small floating, BOTTOM-left of the AA area so it
          never overlaps the clock/presence bar at the top. Returns from AA to
          the landing page. Only visible when viewing AA (not landing). */}
      {anyProjecting && !viewingLanding && !calibrating && (
        <Box
          className="hub-interactive"
          onClick={() => setViewingLanding(true)}
          sx={{
            position: 'absolute',
            bottom: 'clamp(0.75rem, 2vh, 1.5rem)',
            left: 'clamp(0.75rem, 2vw, 1.5rem)',
            zIndex: 10,
            pointerEvents: 'auto',
            width: 'clamp(2.25rem, 7vmin, 3rem)',
            height: 'clamp(2.25rem, 7vmin, 3rem)',
            borderRadius: '50%',
            backgroundColor: 'rgba(0,0,0,0.55)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            color: '#fff',
            fontSize: 'clamp(1.1rem, 3.5vmin, 1.6rem)',
            transition: 'all 200ms cubic-bezier(0.4, 0, 0.2, 1)',
            '&:hover': {
              backgroundColor: 'rgba(0,0,0,0.75)',
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
        <Box className="hub-interactive" sx={{ pointerEvents: 'auto' }}>
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

      {/* [hub] §12.5: settings drawer (gear in the top-right cluster). */}
      <SettingsPanel
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        intent={intent}
        projectingPhone={projectingPhone}
        phones={phones}
        onResetCalibration={handleForgetCalibration}
      />
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

// [hub] §12.6: media transport controls for the bar. Prev / play-pause / next.
// Each button calls window.projection.ipc.sendCommand, which the main process
// forwards as a SendCommand to the active AA driver. AaSession maps
// CommandMapping.play/pause/playPause/next/prev → BUTTON_KEY.MEDIA_* and sends
// a press+release (src/main/services/projection/driver/aa/AaSession.ts:574-578).
// Stateless on purpose — AA owns the real playback state; we only send intents.
function MediaControls() {
  const send = (key: string) => () => {
    window.projection.ipc.sendCommand(key)
  }
  const btn = (label: string, key: string): ReactNode => (
    <Box
      role="button"
      aria-label={label}
      data-testid={`hub-media-${key}`}
      onClick={send(key)}
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 'clamp(2.25rem, 7vmin, 3rem)',
        height: 'clamp(2.25rem, 7vmin, 3rem)',
        borderRadius: '50%',
        cursor: 'pointer',
        fontSize: 'clamp(1.1rem, 3.5vmin, 1.6rem)',
        color: 'inherit',
        transition: 'background-color 160ms ease, transform 120ms ease',
        '&:hover': { backgroundColor: 'rgba(255,255,255,0.08)' },
        '&:active': { transform: 'scale(0.92)', backgroundColor: 'rgba(255,255,255,0.12)' }
      }}
    >
      {label}
    </Box>
  )
  return (
    <Box
      data-testid="hub-media-controls"
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 'clamp(0.5rem, 2vw, 1rem)',
        // keep the row from stealing vertical space when not needed
        marginTop: 'auto'
      }}
    >
      {btn('\u23EE', 'previous')}
      {btn('\u23EF', 'playPause')}
      {btn('\u23ED', 'next')}
    </Box>
  )
}
