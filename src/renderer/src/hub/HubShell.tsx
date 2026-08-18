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
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import SettingsIcon from '@mui/icons-material/Settings'
import { useLiviStore } from '@store/store'
import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
import { buildTouchTransform, displayToTouchNorm, type TouchTransform } from './touchNorm'

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

  // [hub] Phase 1.10: three-state navigation replaces viewingLanding boolean.
  //   screensaver: clock + date + bubbles (opaque, default)
  //   landing: 2x2 tile grid (AA video hidden behind)
  //   aa: transparent shell, AA video visible, touch passthrough
  const [viewMode, setViewMode] = useState<'screensaver' | 'landing' | 'aa'>('screensaver')
  const [calibrating, setCalibrating] = useState(false)
  const [calibrationStep, setCalibrationStep] = useState(0)
  const [calibrationApp, setCalibrationApp] = useState<string | null>(null)
  const [navigating, setNavigating] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const projectingPhone = phones.find((p) => p.presence.level === 'projecting') ?? null

  // [hub] Touch coordinate transform for calibration recording + replay.
  // The AA video is letterboxed inside a 16:9 tier and offset by the bar
  // height. The calibration code must convert display px → normalized tier
  // coords using the same logic as the projection page's norm function
  // (useProjectionTouch.ts). Without this, touches outside the center ~1/3
  // of the display are silently dropped by AaSession's SendTouch handler
  // (out of bounds after letterbox inset subtraction), and scroll sequences
  // for Messages/Music never replay correctly (work-log 22 bug 2).
  //
  // The tier is computed from projectionWidth/Height via matchFittingAAResolution
  // (same as AaSession), NOT from negotiatedWidth/Height — those are never set
  // in the renderer store (no IPC channel sends them from main).
  const liviSettings = useLiviStore((s) => s.settings)
  const touchTransform: TouchTransform | null = useMemo(
    () =>
      buildTouchTransform({
        projectionWidth: liviSettings?.projectionWidth ?? 0,
        projectionHeight: liviSettings?.projectionHeight ?? 0,
        projectionViewAreaTop: liviSettings?.projectionViewAreaTop ?? 0
      }),
    [liviSettings]
  )

  // [hub] Measure the full bar (clock + presence row) and publish as
  // projectionViewAreaTop. Re-runs when phones change (PresenceRow
  // appears/disappears) and when viewMode changes (bar only rendered in
  // landing/aa modes, not screensaver).
  useEffect(() => {
    const el = barRef.current
    if (!el) return
    const publish = (): void => {
      const h = el.getBoundingClientRect().height
      if (h <= 0) return
      // [hub] projectionViewAreaTop is in DISPLAY px (matching
      // projectionWidth/Height — see ServiceDiscoveryBuilder.ts G1 comment,
      // dongleDriver SendViewArea, Projection.tsx ViewAreaMask). In the kiosk
      // renderer, CSS px = physical screen px. When projectionWidth/Height
      // matches the physical screen (the correct configuration — e.g.
      // 600x1024 portrait), display px = screen px = CSS px, so the bar
      // height is published directly with no scaling. The ServiceDiscoveryBuilder
      // then scales display→tier px (sy = vH/displayHeight) when building the
      // AA Service Discovery Response.
      //
      // DO NOT add screen→projection scaling here. The previous scaling code
      // (h * projH / screenH) was a band-aid for a misconfiguration where
      // projectionWidth/Height was 1280x720 (landscape) but the physical panel
      // is 600x1024 (portrait). Scaling cannot fix an orientation mismatch —
      // it just produces wrong values. The fix is to set projectionWidth/
      // Height to match the physical screen (work-log 18, work-log 22).
      onBarHeight(Math.round(h))
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
  }, [onBarHeight, phones.length, viewMode])

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

  // [hub] ring-trace (work-log 27 Bug C): when a ring arrives, log the values
  // that feed the transparency condition so we can tell whether the black
  // banner is caused by projectingStable being false (opaque shell hides AA
  // video) or by the RingBanner's own 0.5 black overlay over a dark AA screen.
  // Re-fires on projectingStable/viewMode/anyProjecting transitions so we see
  // the state evolve while the ring is up.
  useEffect(() => {
    if (!ring) return
    console.log(
      `[ring-trace] HubShell: ring=%o projectingStable=%s viewMode=%s anyProjecting=%s`,
      ring,
      projectingStable,
      viewMode,
      anyProjecting
    )
  }, [ring, projectingStable, viewMode, anyProjecting])

  // [hub] §12.4: tapping a phone bubble selects it (asks LIVI to make it the
  // active session) AND, if it is the phone currently projecting, returns to
  // the landing page so the user can pick an app. Tapping a non-projecting
  // phone's bubble tries to select it (LIVI returns 409 if no session); we do
  // not change the local view in that case.
  const handleBubbleSelect = useCallback(
    (phoneId: string) => {
      const isProjecting = phones.find((p) => p.phoneId === phoneId)?.presence.level === 'projecting'
      if (isProjecting) setViewMode('landing')
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
      setViewMode('screensaver')
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
      setViewMode('screensaver')
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
      // [hub] Send 'home' to reset to the AA dashboard/app grid.
      window.projection.ipc.sendCommand('home')
      // Wait for dashboard to render, then replay the recorded touch sequence.
      setTimeout(() => {
        if (pos && pos.sequence && pos.sequence.length > 0) {
          // Replay recorded touch sequence (scrolls + final tap).
          // [hub] The recorded coordinates are display px (e.clientX/Y from
          // the CalibrationOverlay). Convert to normalized tier coords using
          // displayToTouchNorm, which maps display px → tier content px
          // linearly (no viewAreaTop Y offset — AaSession handles the bar
          // offset via _touchInsetTop). See touchNorm.ts for details.
          const w = window.innerWidth
          const h = window.innerHeight
          let i = 0
          const playNext = () => {
            if (i >= pos.sequence.length) {
              // Wait for the app to open after the final tap.
              setTimeout(onComplete, 800)
              return
            }
            const evt = pos.sequence[i]
            const n = touchTransform
              ? displayToTouchNorm(evt.x, evt.y, touchTransform, w, h)
              : { x: evt.x / w, y: evt.y / h }
            if (n) {
              window.projection.ipc.sendTouch(n.x, n.y, evt.action)
            }
            i++
            // [hub] Use the NEXT event's delay (the time gap between this
            // event and the next), matching the old project's
            // replayTouchSequence (patch_homehub_v2.py line 246). The delay
            // is "ms since previous event", so sequence[i].delay after
            // incrementing i is the gap between event i-1 and event i.
            // Cap at 50ms with 10ms minimum for replay speed (old project).
            if (i < pos.sequence.length) {
              const nextDelay = Math.min(pos.sequence[i].delay, 50)
              setTimeout(playNext, nextDelay < 10 ? 10 : nextDelay)
            } else {
              // Last event sent — wait for app to open.
              setTimeout(onComplete, 800)
            }
          }
          playNext()
        } else if (pos && pos.x !== undefined) {
          // Fallback: just tap the recorded position (no scroll sequence)
          const w = window.innerWidth
          const h = window.innerHeight
          const n = touchTransform
            ? displayToTouchNorm(pos.x, pos.y, touchTransform, w, h)
            : { x: pos.x / w, y: pos.y / h }
          if (n) {
            window.projection.ipc.sendTouch(n.x, n.y, 14)
            setTimeout(() => {
              window.projection.ipc.sendTouch(n.x, n.y, 16)
              setTimeout(onComplete, 800)
            }, 100)
          } else {
            onComplete()
          }
        } else {
          onComplete()
        }
      }, 800)
    },
    [projectingPhone, touchTransform]
  )

  // [hub] Phase 1.10: back button cycles aa → landing → screensaver
  const handleBack = useCallback(() => {
    setViewMode((prev) => {
      if (prev === 'aa') return 'landing'
      if (prev === 'landing') return 'screensaver'
      return prev
    })
  }, [])

  const handleTileTap = useCallback(
    (tile: LandingTile) => {
      if (!projectingPhone) return
      if (tile.calibratable && !isCalibrated(projectingPhone.phoneId, tile.key)) {
        // Start calibration for this specific app
        setCalibrationApp(tile.key)
        setCalibrationStep(1)
        setCalibrating(true)
        // [hub] Send a single 'home' to go to the AA dashboard. The
        // CalibrationOverlay (z-index 100002) appears on the next render and
        // dims the dashboard with rgba(0,0,0,0.35). A single home avoids the
        // double-blink caused by the previous double-home + transition overlay.
        window.projection.ipc.sendCommand('home')
        return
      }
      // Navigate to the app invisibly, then fade to AA
      setNavigating(true)
      navigateToApp(tile.key, () => {
        setNavigating(false)
        setViewMode('aa')
      })
    },
    [projectingPhone, navigateToApp]
  )

  const handleFullApps = useCallback(() => {
    window.projection.ipc.sendCommand('home')
    setViewMode('aa')
  }, [])

  const handleForgetCalibration = useCallback(() => {
    if (!projectingPhone) return
    clearCalibration(projectingPhone.phoneId)
    setViewMode('landing') // re-render landing with uncalibrated tiles
  }, [projectingPhone])

  // [hub] Phase 1.10: per-app recalibration from settings
  const handleRecalibrateApp = useCallback(
    (phoneId: string, appKey: string) => {
      if (!projectingPhone || projectingPhone.phoneId !== phoneId) return
      setSettingsOpen(false)
      setViewMode('landing')
      setCalibrationApp(appKey)
      setCalibrationStep(1)
      setCalibrating(true)
      // [hub] Single home — see handleTileTap comment.
      window.projection.ipc.sendCommand('home')
    },
    [projectingPhone]
  )

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
        // Continue to next app — do NOT re-send home. The old project
        // (patch_homehub_v2.py) only sends home once at calibration start,
        // then just shows the next overlay. Re-sending home resets the
        // dashboard scroll position, so the user has to scroll again to
        // find the next app — and the CalibrationOverlay remounts (via
        // key={calibrationApp}) so its refs are clean.
        setCalibrationApp(nextApp.key)
        setCalibrationStep((s) => s + 1)
      } else {
        // All apps calibrated — return to landing
        setCalibrating(false)
        setCalibrationApp(null)
        setCalibrationStep(0)
        setViewMode('landing')
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
      // Continue to next app — no home re-send (see handleCalibrationRecord).
      setCalibrationApp(nextApp.key)
      setCalibrationStep((s) => s + 1)
    } else {
      setCalibrating(false)
      setCalibrationApp(null)
      setCalibrationStep(0)
      setViewMode('landing')
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
  // [hub] Phase 1.10: hub-aa-mode is driven by viewMode === 'aa' only.
  // During calibration, the CalibrationOverlay (z-index 100002) handles its own
  // pointer events; we don't want hub-aa-mode's pointer-events:none on
  // #hub-shell-root to interfere.
  const aaMode = viewMode === 'aa'
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
        // [hub] §12.2: transparent when in AA mode OR calibrating (AA dashboard
        // must be visible through the semi-transparent overlay). During landing
        // and screensaver, opaque covers the AA video.
        // [hub] Fix 1 (work-log 27): also transparent when a ring is active and a
        // phone is projecting, so the AA video + AA's native call UI show through
        // behind the RingBanner. Otherwise the opaque t.bg hides the AA video and
        // the user sees a black screen with the banner card on top.
        // Uses the latched `projectingStable` so a presence blip cannot flash
        // an opaque background over the video mid-touch.
        backgroundColor:
          projectingStable && (viewMode !== 'screensaver' || !!ring)
            ? 'transparent'
            : t.bg,
        color: t.text,
        overflow: 'hidden'
        // pointer-events is intentionally NOT set here: the CSS rule
        // `html.hub-aa-mode #hub-shell-root { pointer-events: none }` is the
        // single source of truth for AA-mode passthrough, and `.hub-interactive`
        // children re-enable it. Setting it inline would override the CSS
        // (inline > rule) and reintroduce the flicker bug.
      }}
    >
      {/* [hub] Phase 1.10: top-right cluster — back button + gear + health dot.
          Always visible (including screensaver). Back button cycles
          aa → landing → screensaver; hidden on screensaver. Gear opens the
          settings drawer (§12.5). All stay tappable in AA mode via
          .hub-interactive. */}
      <Box
        className="hub-interactive"
        sx={{
          position: 'absolute',
          top: '0.6rem',
          right: '0.6rem',
          zIndex: 10,
          pointerEvents: 'auto',
          display: 'flex',
          alignItems: 'center',
          gap: '0.4rem'
        }}
      >
        {viewMode !== 'screensaver' && (
          <IconButton
            aria-label="Back"
            data-testid="hub-back-button"
            onClick={handleBack}
            size="small"
            sx={{ color: t.text, opacity: 0.85, '&:hover': { opacity: 1, backgroundColor: 'rgba(255,255,255,0.08)' } }}
          >
            <ArrowBackIcon fontSize="small" />
          </IconButton>
        )}
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

      {/* [hub] Phase 1.10: Screensaver mode — clock + date + bubbles (opaque).
          [hub] Fix 1 (work-log 27): hidden when a ring is active so the AA video
          and native call UI show through behind the RingBanner. */}
      {viewMode === 'screensaver' && !ring && (
        <Screensaver
          message={connecting ? 'Connecting to the hub…' : phones.length === 0 ? 'Dock a phone to begin' : undefined}
          subtitle={
            phones.length > 0 && !connecting
              ? `${greeting(new Date())} · ${homePhones.length === 0 ? 'Nobody is home right now' : homePhones.length === phones.length ? 'Everyone is home' : `${homePhones.length} of ${phones.length} home`}`
              : undefined
          }
          phones={phones}
          onSelect={handleBubbleSelect}
        />
      )}

      {/* [hub] Phase 1.10: Landing / AA mode — bar + content.
          Bar hidden during calibration so the full AA dashboard is visible
          through the CalibrationOverlay.
          [hub] Fix 1 (work-log 27): bar also hidden during a ring so the AA
          video + native call UI show through behind the RingBanner. */}
      {viewMode !== 'screensaver' && !calibrating && !ring && (
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
              // [hub] Bar minHeight targets ~450px on a 1024px portrait panel
              // (44vh = 450px). This leaves ~574px for AA — a nearly square
              // 600×574 hole (AR ~1.04). In portrait AA, Google Maps is the
              // "base layer" (top, largest area). A tall AA area gives Maps too
              // much space and pushes app launcher / media to the disconnected
              // bottom. A near-square area balances Maps and apps. The old
              // project used projectionViewAreaTop: 450 (work-log 18, r3 config).
              // This minHeight was removed in work-log 21 by mistake — restored
              // now that the screen→projection scaling band-aid is gone.
              minHeight: 'clamp(380px, 44vh, 480px)'
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
              // [hub] No padding here — the Landing component has its own
              // padding. Extra padding on this Box creates a gap where the
              // AA video shows through (the HubShell is transparent when
              // projecting), making the landing appear "skinny" after
              // back-navigation from AA mode (work-log 22 bug 1).
              textAlign: 'center'
              // [hub] §12.2: pointer-events handled by the `hub-aa-mode` CSS
              // (none on #hub-shell-root, auto on .hub-interactive). This Box
              // is not interactive in AA mode, so it inherits `none` and lets
              // touches fall through to #projection-root below.
            }}
          >
            {/* [hub] §12.4: landing page — tiles on top of the AA video.
                Hidden during calibration so AA dashboard is visible through
                the semi-transparent CalibrationOverlay. */}
            {viewMode === 'landing' && !calibrating && projectingPhone && (
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
          key={calibrationApp}
          appLabel={calibrationApp.charAt(0).toUpperCase() + calibrationApp.slice(1)}
          appIcon={LANDING_TILES.find((t) => t.key === calibrationApp)?.icon ?? '?'}
          step={calibrationStep}
          totalSteps={3}
          onRecord={handleCalibrationRecord}
          onSkip={handleCalibrationSkip}
          touchTransform={touchTransform}
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
        onRecalibrateApp={handleRecalibrateApp}
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
        '&:hover': { transform: 'scale(0.92)', backgroundColor: 'rgba(255,255,255,0.12)' }
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
      {btn('\u23EE', 'prev')}
      {btn('\u23EF', 'playPause')}
      {btn('\u23ED', 'next')}
    </Box>
  )
}
