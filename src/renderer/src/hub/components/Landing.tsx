// [hub] §12.4/§12.6: the landing page — shown when a phone is docked and
// projecting, before the user enters AA. A 2x2 tile grid gives quick access
// to Phone, Messages, Music, and the full AA apps grid.
//
// The landing page is a z-layer overlay WITHIN the projection surface (not a
// separate SurfaceManager surface — projection is priority 70, landing is 30,
// so projection preempts). HubShell manages local viewingLanding vs viewingAA
// state. The AA video runs underneath; the landing page fades out to reveal it.
//
// Calibration: when a user taps an uncalibrated tile, a calibration flow
// records the touch position of each app on the AA dashboard. The recorded
// sequence is replayed invisibly (sendCommand('home') + touch replay) to jump
// directly to the app, then the landing page fades out. Data is stored in
// localStorage per phone.

import { Box, Typography } from '@mui/material'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useHubTokens } from '../useHubTokens'
import type { HubPhone } from '../types'

export type LandingTile = {
  key: string
  label: string
  icon: string
  // Whether this tile needs calibration (Phone, Messages, Music do; Apps doesn't)
  calibratable: boolean
}

const TILES: LandingTile[] = [
  { key: 'phone', label: 'Phone', icon: '\u{1F4DE}', calibratable: true },
  { key: 'messages', label: 'Messages', icon: '\u{1F4AC}', calibratable: true },
  { key: 'music', label: 'Music', icon: '\u{1F3B5}', calibratable: true },
  { key: 'apps', label: 'Apps', icon: '\u{25A6}', calibratable: false }
]

export interface LandingProps {
  phone: HubPhone
  onTileTap: (tile: LandingTile) => void
  onFullApps: () => void
  onForgetCalibration?: () => void
}

// --- Calibration data persistence ---

interface CalibData {
  x: number
  y: number
  sequence: { x: number; y: number; action: number; delay: number }[]
}

function loadCalibration(phoneId: string): Record<string, CalibData> {
  try {
    const raw = localStorage.getItem(`homehub.appPositions.${phoneId}`)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function saveCalibration(phoneId: string, data: Record<string, CalibData>): void {
  try {
    localStorage.setItem(`homehub.appPositions.${phoneId}`, JSON.stringify(data))
  } catch {
    // ignore
  }
}

export function isCalibrated(phoneId: string, appKey: string): boolean {
  const data = loadCalibration(phoneId)
  return data[appKey] !== undefined
}

export function getCalibration(phoneId: string, appKey: string): CalibData | null {
  const data = loadCalibration(phoneId)
  return data[appKey] ?? null
}

export function clearCalibration(phoneId: string): void {
  try {
    localStorage.removeItem(`homehub.appPositions.${phoneId}`)
  } catch {
    // ignore
  }
}

// --- Component ---

export function Landing({ phone, onTileTap, onFullApps, onForgetCalibration }: LandingProps) {
  const t = useHubTokens()
  const [calibData, setCalibData] = useState(() => loadCalibration(phone.phoneId))
  const personName = phone.person?.name ?? 'Unknown'
  const personColor = phone.person?.colour ?? '#4F7CAC'
  const personAvatar = phone.person?.avatar
  const isPrimary = phone.person?.isPrimary

  // Reload calibration when phone changes
  useEffect(() => {
    setCalibData(loadCalibration(phone.phoneId))
  }, [phone.phoneId])

  return (
    <Box
      data-testid="hub-landing"
      sx={{
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'flex-start',
        gap: 'clamp(0.75rem, 2vh, 1.5rem)',
        padding: 'clamp(0.75rem, 2vw, 1.5rem)',
        backgroundColor: t.bg,
        zIndex: 5,
        transition: 'opacity 400ms cubic-bezier(0.4, 0, 0.2, 1)',
        pointerEvents: 'auto',
        overflow: 'hidden'
      }}
    >
      {/* [hub] §12.6: person-colored header — makes it instantly clear whose
          phone is active. The accent bar uses the person's colour, and the
          name + avatar are the first thing the user sees. */}
      <Box
        sx={{
          width: '100%',
          maxWidth: '500px',
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
          padding: '0.5rem 0'
        }}
      >
        {/* Person colour accent bar */}
        <Box
          sx={{
            width: '4px',
            height: 'clamp(2rem, 6vh, 3rem)',
            borderRadius: '2px',
            backgroundColor: personColor,
            flexShrink: 0
          }}
        />
        {/* Avatar (if available) or initials */}
        {personAvatar ? (
          <Box
            component="img"
            src={personAvatar}
            sx={{
              width: 'clamp(2rem, 6vh, 3rem)',
              height: 'clamp(2rem, 6vh, 3rem)',
              borderRadius: '50%',
              objectFit: 'cover',
              flexShrink: 0
            }}
          />
        ) : (
          <Box
            sx={{
              width: 'clamp(2rem, 6vh, 3rem)',
              height: 'clamp(2rem, 6vh, 3rem)',
              borderRadius: '50%',
              backgroundColor: personColor,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
              color: '#fff',
              fontSize: 'clamp(1rem, 3vh, 1.5rem)',
              fontWeight: 500
            }}
          >
            {personName.charAt(0).toUpperCase()}
          </Box>
        )}
        <Box sx={{ display: 'flex', flexDirection: 'column' }}>
          <Typography
            sx={{
              fontSize: 'clamp(1.1rem, 4vmin, 1.8rem)',
              fontWeight: 500,
              lineHeight: 1.2
            }}
          >
            {personName}&apos;s Phone
          </Typography>
          {isPrimary && (
            <Typography sx={{ fontSize: '0.75rem', color: t.textMuted }}>
              Primary phone
            </Typography>
          )}
        </Box>
      </Box>

      {/* 2x2 tile grid */}
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 'clamp(0.75rem, 2vw, 1.25rem)',
          width: '100%',
          maxWidth: '500px',
          flex: 1,
          alignContent: 'center'
        }}
      >
        {TILES.map((tile) => {
          const calibrated = !tile.calibratable || calibData[tile.key] !== undefined
          return (
            <Box
              key={tile.key}
              role="button"
              tabIndex={0}
              data-testid={`landing-tile-${tile.key}`}
              onClick={() => {
                if (tile.key === 'apps') {
                  onFullApps()
                } else {
                  onTileTap(tile)
                }
              }}
              sx={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '0.5rem',
                aspectRatio: '1.5',
                borderRadius: '16px',
                backgroundColor: 'rgba(255,255,255,0.03)',
                border: '1px solid rgba(255,255,255,0.05)',
                cursor: 'pointer',
                transition: 'all 200ms cubic-bezier(0.4, 0, 0.2, 1)',
                opacity: calibrated ? 1 : 0.5,
                '&:hover': {
                  backgroundColor: 'rgba(255,255,255,0.06)'
                },
                '&:active': {
                  transform: 'scale(0.95)',
                  backgroundColor: 'rgba(255,255,255,0.06)'
                }
              }}
            >
              <Typography sx={{ fontSize: 'clamp(2rem, 8vmin, 3rem)' }}>
                {tile.icon}
              </Typography>
              <Typography sx={{ fontSize: 'clamp(0.9rem, 3vmin, 1.2rem)', fontWeight: 400 }}>
                {tile.label}
              </Typography>
              {!calibrated && (
                <Typography
                  sx={{ fontSize: '0.7rem', color: t.textMuted, fontStyle: 'italic' }}
                >
                  Setup needed
                </Typography>
              )}
            </Box>
          )
        })}
      </Box>

      {/* Bottom links: Full Apps Grid + Reset calibration */}
      <Box sx={{ display: 'flex', gap: '1.5rem', alignItems: 'center' }}>
        <Typography
          onClick={onFullApps}
          sx={{
            fontSize: 'clamp(0.8rem, 2.5vmin, 1rem)',
            color: '#58a6ff',
            cursor: 'pointer',
            textDecoration: 'none',
            '&:hover': { textDecoration: 'underline' }
          }}
        >
          Full Apps Grid →
        </Typography>
        {onForgetCalibration && Object.keys(calibData).length > 0 && (
          <Typography
            onClick={onForgetCalibration}
            sx={{
              fontSize: 'clamp(0.75rem, 2vmin, 0.9rem)',
              color: t.textMuted,
              cursor: 'pointer',
              '&:hover': { color: t.text, textDecoration: 'underline' }
            }}
          >
            Reset calibration
          </Typography>
        )}
      </Box>
    </Box>
  )
}

// --- Calibration overlay ---

export interface CalibrationOverlayProps {
  appLabel: string
  appIcon: string
  step: number
  totalSteps: number
  onRecord: (x: number, y: number, sequence: { x: number; y: number; action: number; delay: number }[]) => void
  onSkip: () => void
}

export function CalibrationOverlay({
  appLabel,
  appIcon,
  step,
  totalSteps,
  onRecord,
  onSkip
}: CalibrationOverlayProps) {
  const t = useHubTokens()
  const [recording, setRecording] = useState(false)
  const pointerDownPos = useRef<{ x: number; y: number } | null>(null)
  const scrolling = useRef(false)
  const pendingMoves = useRef<{ x: number; y: number }[]>([])
  const stepSequence = useRef<{ x: number; y: number; action: number; delay: number }[]>([])
  const startTime = useRef(0)
  const lastEventTime = useRef(0)

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    e.preventDefault()
    pointerDownPos.current = { x: e.clientX, y: e.clientY }
    scrolling.current = false
    pendingMoves.current = []
    if (startTime.current === 0) startTime.current = Date.now()
    const now = Date.now()
    const delay = now - (lastEventTime.current || startTime.current)
    lastEventTime.current = now
    stepSequence.current.push({ x: e.clientX, y: e.clientY, action: 14, delay })
    setRecording(true)
  }, [])

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!pointerDownPos.current) return
      e.preventDefault()
      const dx = e.clientX - pointerDownPos.current.x
      const dy = e.clientY - pointerDownPos.current.y
      const dist = Math.sqrt(dx * dx + dy * dy)
      const now = Date.now()
      const delay = now - lastEventTime.current
      lastEventTime.current = now

      if (!scrolling.current) {
        if (dist > 8) {
          // Scroll detected — send deferred DOWN + buffered moves to AA
          scrolling.current = true
          window.projection.ipc.sendTouch(
            pointerDownPos.current.x / window.innerWidth,
            pointerDownPos.current.y / window.innerHeight,
            14
          )
          for (const m of pendingMoves.current) {
            window.projection.ipc.sendTouch(m.x / window.innerWidth, m.y / window.innerHeight, 15)
          }
          pendingMoves.current = []
        } else {
          pendingMoves.current.push({ x: e.clientX, y: e.clientY })
          stepSequence.current.push({ x: e.clientX, y: e.clientY, action: 15, delay })
          return
        }
      }
      // Scrolling — forward to AA
      stepSequence.current.push({ x: e.clientX, y: e.clientY, action: 15, delay })
      window.projection.ipc.sendTouch(e.clientX / window.innerWidth, e.clientY / window.innerHeight, 15)
    },
    []
  )

  const handlePointerUp = useCallback(
    (e: React.PointerEvent) => {
      if (!pointerDownPos.current) return
      e.preventDefault()
      const now = Date.now()
      const delay = now - lastEventTime.current
      lastEventTime.current = now
      const dx = e.clientX - pointerDownPos.current.x
      const dy = e.clientY - pointerDownPos.current.y
      const dist = Math.sqrt(dx * dx + dy * dy)

      if (scrolling.current) {
        // Was a scroll — send UP to AA
        stepSequence.current.push({ x: e.clientX, y: e.clientY, action: 16, delay })
        window.projection.ipc.sendTouch(e.clientX / window.innerWidth, e.clientY / window.innerHeight, 16)
        pointerDownPos.current = null
        scrolling.current = false
        // Don't advance — user is still looking
      } else if (dist < 15) {
        // TAP — record only, don't forward to AA
        stepSequence.current.push({ x: e.clientX, y: e.clientY, action: 16, delay })
        onRecord(e.clientX, e.clientY, stepSequence.current.slice())
        stepSequence.current = []
        startTime.current = 0
        pointerDownPos.current = null
        setRecording(false)
      }
    },
    [onRecord]
  )

  return (
    <Box
      data-testid="calibration-overlay"
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      sx={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: 100002,
        backgroundColor: 'rgba(0,0,0,0.5)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'flex-start',
        paddingTop: '10vh',
        touchAction: 'none'
      }}
    >
      <Box
        sx={{
          backgroundColor: 'rgba(13,17,23,0.95)',
          borderRadius: '16px',
          padding: '1.5rem 2rem',
          textAlign: 'center',
          border: '1px solid rgba(255,255,255,0.1)',
          maxWidth: '80%'
        }}
      >
        <Typography sx={{ fontSize: '2rem', marginBottom: '0.5rem' }}>{appIcon}</Typography>
        <Typography sx={{ fontSize: '1.2rem', fontWeight: 400, marginBottom: '0.5rem' }}>
          Tap your {appLabel} app
        </Typography>
        <Typography sx={{ fontSize: '0.9rem', color: t.textMuted, marginBottom: '1rem' }}>
          Step {step} of {totalSteps} — scroll to find it, then tap it
        </Typography>
        <Typography
          onClick={onSkip}
          sx={{
            fontSize: '0.85rem',
            color: '#58a6ff',
            cursor: 'pointer',
            '&:hover': { textDecoration: 'underline' }
          }}
        >
          Skip this app
        </Typography>
      </Box>
    </Box>
  )
}

export { TILES as LANDING_TILES, loadCalibration, saveCalibration }
export type { CalibData }
