// [hub] Phase 6 — the in-call UI (§12.6 state A).
//
// Replaces the RingBanner when ring.state === 'active'. Shows the caller,
// a live call timer, and three controls: Mute, End Call, and Move to phone /
// Take back on hub. No DTMF keypad — the user can dial from AA/CarPlay.
//
// Design mirrors RingBanner: same card layout, same tokens, same 9mm button
// floor. The ambient glow is calmer (no pulse) — the call is already answered.
import { Box, Button, Typography } from '@mui/material'
import { useEffect, useState } from 'react'
import type { HubRing } from '../types'
import { useHubTokens } from '../useHubTokens'

export interface InCallViewProps {
  ring: HubRing
  /** Number of known phones — when >1, "on <person>" is shown. */
  knownPhoneCount: number
  onEnd?: (phoneId: string) => void
  onMute?: (phoneId: string) => void
  onMoveToPhone?: (phoneId: string) => void
  onTakeBackOnHub?: (phoneId: string) => void
}

const BUTTON_SX = {
  minWidth: '9mm',
  minHeight: '9mm',
  fontSize: 'clamp(1rem, 4vmin, 1.6rem)',
  fontWeight: 500,
  borderRadius: '14px',
  paddingInline: 'clamp(1.2rem, 4vw, 2.4rem)',
  textTransform: 'none' as const
}

/** Format seconds as m:ss or h:mm:ss. */
function formatDuration(totalSeconds: number): string {
  const h = Math.floor(totalSeconds / 3600)
  const m = Math.floor((totalSeconds % 3600) / 60)
  const s = totalSeconds % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

export function InCallView({
  ring,
  knownPhoneCount,
  onEnd,
  onMute,
  onMoveToPhone,
  onTakeBackOnHub
}: InCallViewProps) {
  const t = useHubTokens()
  const callerName = ring.caller.name ?? ring.caller.number ?? 'Active call'
  const showPerson = knownPhoneCount > 1 && ring.person
  const isMuted = ring.muted ?? false
  const audioRoute = ring.audioRoute ?? 'hub'
  const canMoveAudio = ring.answerVia === 'hfp'

  // Live call timer — ticks every second from activeAt.
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    const base = ring.activeAt ?? ring.startedAt
    if (!base) return
    const tick = () => setElapsed(Math.floor((Date.now() - base) / 1000))
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [ring.activeAt, ring.startedAt])

  return (
    <Box
      data-testid="hub-in-call"
      role="status"
      aria-live="polite"
      sx={{
        position: 'absolute',
        inset: 0,
        zIndex: 100,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        // Calmer than RingBanner: solid dim, no pulse. The call is answered.
        backgroundColor: 'rgba(0,0,0,0.45)',
        animation: 'hub-ring-in 300ms cubic-bezier(0.16, 1, 0.3, 1)'
      }}
    >
      <Box
        sx={{
          position: 'relative',
          zIndex: 1,
          width: 'min(92%, 540px)',
          backgroundColor: t.surface,
          color: t.text,
          borderRadius: '20px',
          border: `1px solid ${t.border}`,
          boxShadow: '0 12px 40px rgba(0,0,0,0.4)',
          padding: 'clamp(1.2rem, 4vw, 2rem)',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.6rem',
          textAlign: 'center',
          animation: 'hub-ring-card-in 300ms cubic-bezier(0.16, 1, 0.3, 1)'
        }}
      >
        {/* In-call indicator */}
        <Box sx={{ fontSize: 'clamp(1.6rem, 7vmin, 2.6rem)', lineHeight: 1 }}>
          {isMuted ? '🔇' : '📞'}
        </Box>

        {/* Caller name — largest text, same as RingBanner */}
        <Typography
          sx={{ fontSize: 'clamp(1.6rem, 8vmin, 3rem)', fontWeight: 600, lineHeight: 1.1 }}
        >
          {callerName}
        </Typography>

        {/* Person + timer row */}
        {showPerson && (
          <Typography sx={{ color: t.textMuted, fontSize: 'clamp(1rem, 4vmin, 1.4rem)' }}>
            on {ring.person}
          </Typography>
        )}
        <Typography
          data-testid="hub-in-call-timer"
          sx={{
            color: t.textMuted,
            fontSize: 'clamp(1.2rem, 5vmin, 1.8rem)',
            fontVariantNumeric: 'tabular-nums',
            letterSpacing: '0.05em'
          }}
        >
          {formatDuration(elapsed)}
        </Typography>

        {/* Muted indicator */}
        {isMuted && (
          <Typography sx={{ color: t.warn, fontSize: 'clamp(0.9rem, 3.5vmin, 1.2rem)' }}>
            Mic muted
          </Typography>
        )}

        {/* Audio route indicator */}
        {canMoveAudio && (
          <Typography sx={{ color: t.textMuted, fontSize: 'clamp(0.85rem, 3vmin, 1.1rem)' }}>
            Audio on {audioRoute === 'hub' ? 'hub' : 'phone'}
          </Typography>
        )}

        {/* Queued call (call waiting) */}
        {ring.queued.length > 0 && (
          <Typography sx={{ color: t.warn, fontSize: 'clamp(0.85rem, 3vmin, 1.1rem)' }}>
            ⏳ Waiting: {ring.queued.map((q) => q.person ?? q.caller.name ?? 'Unknown').join(', ')}
          </Typography>
        )}

        {/* Primary controls */}
        <Box sx={{ display: 'flex', gap: '0.75rem', justifyContent: 'center', mt: '0.4rem' }}>
          <Button
            variant="contained"
            color="error"
            sx={BUTTON_SX}
            onClick={() => onEnd?.(ring.phoneId)}
            data-testid="hub-in-call-end"
          >
            End Call
          </Button>
          <Button
            variant="contained"
            color={isMuted ? 'warning' : 'primary'}
            sx={BUTTON_SX}
            onClick={() => onMute?.(ring.phoneId)}
            data-testid="hub-in-call-mute"
          >
            {isMuted ? 'Unmute' : 'Mute'}
          </Button>
        </Box>

        {/* Audio routing — only for HFP calls */}
        {canMoveAudio && (
          <Box sx={{ display: 'flex', gap: '0.5rem', justifyContent: 'center', flexWrap: 'wrap' }}>
            {audioRoute === 'hub' ? (
              <Button
                size="small"
                sx={{ color: t.textMuted, textTransform: 'none' }}
                onClick={() => onMoveToPhone?.(ring.phoneId)}
                data-testid="hub-in-call-move-to-phone"
              >
                Move to phone
              </Button>
            ) : (
              <Button
                size="small"
                sx={{ color: t.textMuted, textTransform: 'none' }}
                onClick={() => onTakeBackOnHub?.(ring.phoneId)}
                data-testid="hub-in-call-take-back"
              >
                Take back on hub
              </Button>
            )}
          </Box>
        )}
      </Box>

      <style>{`
        @keyframes hub-ring-in { from { opacity: 0 } to { opacity: 1 } }
        @keyframes hub-ring-card-in {
          from { opacity: 0; transform: translateY(12px) scale(0.94) }
          to   { opacity: 1; transform: translateY(0) scale(1) }
        }
        @media (prefers-reduced-motion: reduce) {
          [data-testid="hub-in-call"], [data-testid="hub-in-call"] * {
            animation: none !important;
          }
        }
      `}</style>
    </Box>
  )
}
