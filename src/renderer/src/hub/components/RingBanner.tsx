// [hub] Phase 2.3 — the ring banner (§12.6 state E, §9.1).
//
// The one place ambiguity is forbidden. The caller's name is the largest text on
// screen. "calling <person>" is shown when more than one phone is known. Buttons
// are >= 9mm (physical units, §12.1) — this is tapped in a hurry, at arm's length.
//
// `canAnswerOnHub: false` changes the LABEL, never removes the banner: the
// promise is "you will know" — knowing and walking to the phone is still
// infinitely better than missing it. `[Bring to hub]` appears ONLY when
// `HubState.ring.canBringToHub` is true; a dead button here is the worst place
// in the product to have one (§12.6).
//
// The banner is a z-layer over whatever is on screen (§12.2). Motion is
// subordinate to the latency budget (§9.1 R-2): the buttons are live before any
// entrance animation finishes.
import { Box, Button, Typography } from '@mui/material'
import type { HubRing } from '../types'
import { useHubTokens } from '../useHubTokens'

export interface RingBannerProps {
  ring: HubRing
  /** Number of known phones — when >1, "calling <person>" is shown (§12.6). */
  knownPhoneCount: number
  onAnswer?: (phoneId: string) => void
  onDecline?: (phoneId: string) => void
  onSilence?: (phoneId: string) => void
  onBringToHub?: (phoneId: string) => void
}

// >= 9mm at ~96dpi ≈ 34px; use a fluid floor so it scales on a big panel too.
const BUTTON_SX = {
  minWidth: '9mm',
  minHeight: '9mm',
  fontSize: 'clamp(1rem, 4vmin, 1.6rem)',
  fontWeight: 500,
  borderRadius: '14px',
  paddingInline: 'clamp(1.2rem, 4vw, 2.4rem)',
  textTransform: 'none' as const
}

export function RingBanner({
  ring,
  knownPhoneCount,
  onAnswer,
  onDecline,
  onSilence,
  onBringToHub
}: RingBannerProps) {
  const t = useHubTokens()
  const callerName = ring.caller.name ?? ring.caller.number ?? 'Incoming call'
  const showPerson = knownPhoneCount > 1 && ring.person
  const answerLabel = ring.canAnswerOnHub ? 'Answer' : 'Answer on phone'

  return (
    <Box
      data-testid="hub-ring-banner"
      role="alert"
      aria-live="assertive"
      sx={{
        position: 'absolute',
        inset: 0,
        zIndex: 100,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        // A dim base for legibility over projection, plus a warm lamp-like glow
        // (DESIGN_VISION: "a soft warmth — not red, not alarming, more like the
        // glow of a lamp turning on"). The glow breathes on a 2 s cycle — it is
        // alive, not flashing. Rendered on ::before so it can pulse independently.
        backgroundColor: 'rgba(0,0,0,0.5)',
        '&::before': {
          content: '""',
          position: 'absolute',
          inset: 0,
          pointerEvents: 'none',
          background:
            'radial-gradient(120% 90% at 50% 44%, rgba(255,150,90,0.24) 0%, ' +
            'rgba(255,107,107,0.12) 40%, rgba(0,0,0,0) 74%)',
          animation: 'hub-ambient-pulse 2s ease-in-out infinite'
        },
        // The banner *arrives* (DESIGN_VISION), but the buttons are live
        // immediately — animation never gates the action (§9.1 R-2).
        animation: 'hub-ring-in 300ms cubic-bezier(0.16, 1, 0.3, 1)'
      }}
    >
      <Box
        sx={{
          // Above the ambient glow (::before) so the card stays crisp.
          position: 'relative',
          zIndex: 1,
          width: 'min(92%, 540px)',
          backgroundColor: t.surface,
          color: t.text,
          borderRadius: '20px',
          border: `1px solid ${t.border}`,
          // A soft warm halo under the card reinforces the lamp feeling.
          boxShadow: '0 12px 40px rgba(0,0,0,0.4), 0 0 60px rgba(255,140,90,0.18)',
          padding: 'clamp(1.2rem, 4vw, 2rem)',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.6rem',
          textAlign: 'center',
          // The card springs in — "someone walking into the room" (DESIGN_VISION).
          animation: 'hub-ring-card-in 300ms cubic-bezier(0.16, 1, 0.3, 1)'
        }}
      >
        {/* Phone icon + caller name: the largest text on screen (§12.6). */}
        <Box sx={{ fontSize: 'clamp(2rem, 9vmin, 3.4rem)', lineHeight: 1 }}>📞</Box>
        <Typography
          sx={{ fontSize: 'clamp(1.6rem, 8vmin, 3rem)', fontWeight: 600, lineHeight: 1.1 }}
        >
          {callerName}
        </Typography>
        {showPerson && (
          <Typography sx={{ color: t.textMuted, fontSize: 'clamp(1rem, 4vmin, 1.4rem)' }}>
            calling {ring.person}
          </Typography>
        )}

        {/* Queued call: compact second row (§9.5). */}
        {ring.queued.length > 0 && (
          <Typography sx={{ color: t.textMuted, fontSize: 'clamp(0.85rem, 3vmin, 1.1rem)' }}>
            also: {ring.queued.map((q) => q.person ?? 'Unknown').join(', ')}
          </Typography>
        )}

        {/* Buttons. [Bring to hub] only when canBringToHub. A dead button here
            is the worst place in the product to have one (§12.6). */}
        <Box sx={{ display: 'flex', gap: '0.75rem', justifyContent: 'center', mt: '0.4rem' }}>
          <Button
            variant="contained"
            color="error"
            sx={BUTTON_SX}
            onClick={() => onDecline?.(ring.phoneId)}
            data-testid="hub-ring-decline"
          >
            Decline
          </Button>
          <Button
            variant="contained"
            color="success"
            sx={BUTTON_SX}
            onClick={() => onAnswer?.(ring.phoneId)}
            data-testid="hub-ring-answer"
          >
            {answerLabel}
          </Button>
        </Box>

        <Box sx={{ display: 'flex', gap: '0.5rem', justifyContent: 'center', flexWrap: 'wrap' }}>
          {ring.tone && (
            <Button
              size="small"
              sx={{ color: t.textMuted, textTransform: 'none' }}
              onClick={() => onSilence?.(ring.phoneId)}
              data-testid="hub-ring-silence"
            >
              Silence
            </Button>
          )}
          {ring.canBringToHub && (
            <Button
              size="small"
              sx={{ color: t.textMuted, textTransform: 'none' }}
              onClick={() => onBringToHub?.(ring.phoneId)}
              data-testid="hub-ring-bring-to-hub"
            >
              Bring to hub
            </Button>
          )}
        </Box>
      </Box>

      <style>{`
        @keyframes hub-ring-in { from { opacity: 0 } to { opacity: 1 } }
        @keyframes hub-ring-card-in {
          from { opacity: 0; transform: translateY(12px) scale(0.94) }
          to   { opacity: 1; transform: translateY(0) scale(1) }
        }
        @keyframes hub-ambient-pulse {
          0%, 100% { opacity: 0.55 }
          50% { opacity: 1 }
        }
        @media (prefers-reduced-motion: reduce) {
          [data-testid="hub-ring-banner"], [data-testid="hub-ring-banner"] * {
            animation: none !important;
          }
        }
      `}</style>
    </Box>
  )
}
