// [hub] G2 / §5.3.2 — the enrollment sheet. "Also reach this phone when it's
// not docked" → phone.enrolStart mints a 6-digit code (and QR) shown here for
// the user to scan in the companion app. The code is single-use, 120s, and only
// exists while the phone is docked. This is the on-ramp to Tier 1 (companion).
import { Box, Button, Modal, Typography } from '@mui/material'
import { useEffect, useState } from 'react'
import type { HubPhone } from '../types'
import { useHubTokens } from '../useHubTokens'

export interface EnrolSheetProps {
  phone: HubPhone
  open: boolean
  onClose: () => void
  onEnrolStart?: (phoneId: string) => Promise<{ code?: string } | void> | void
}

export function EnrolSheet({ phone, open, onClose, onEnrolStart }: EnrolSheetProps) {
  const t = useHubTokens()
  const [code, setCode] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open || !onEnrolStart) return
    setError(null)
    Promise.resolve(onEnrolStart(phone.phoneId))
      .then((r: { code?: string } | void | undefined) => {
        const c = (r && (r as { code?: string }).code) ?? null
        setCode(c)
        if (!c) setError('Could not generate a code. Try again.')
      })
      .catch(() => setError('Could not reach the hub.'))
  }, [open, phone.phoneId, onEnrolStart])

  return (
    <Modal open={open} onClose={onClose} aria-label="Enroll this phone">
      <Box
        data-testid="hub-enrol-sheet"
        sx={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          width: 'min(92%, 460px)',
          backgroundColor: t.surface,
          color: t.text,
          borderRadius: '16px',
          border: `1px solid ${t.border}`,
          padding: 'clamp(1.2rem, 4vw, 2rem)',
          display: 'flex',
          flexDirection: 'column',
          gap: '1rem',
          textAlign: 'center'
        }}
      >
        <Typography sx={{ fontSize: 'clamp(1.1rem, 4.5vmin, 1.6rem)', fontWeight: 600 }}>
          Reach this phone anywhere in the house
        </Typography>
        <Typography sx={{ color: t.textMuted, fontSize: 'clamp(0.85rem, 3vmin, 1rem)' }}>
          Install the Hearth companion app on {phone.person?.name ?? 'this phone'} and scan the
          code, or enter these digits. The code expires in 2 minutes.
        </Typography>
        {error && (
          <Typography sx={{ color: t.danger }} data-testid="hub-enrol-error">
            {error}
          </Typography>
        )}
        {code && (
          <Box
            data-testid="hub-enrol-code"
            sx={{
              fontSize: 'clamp(2rem, 12vmin, 3.5rem)',
              fontWeight: 700,
              letterSpacing: '0.4rem',
              fontFamily: 'monospace',
              padding: '0.5rem 0'
            }}
          >
            {code}
          </Box>
        )}
        <Typography sx={{ color: t.textMuted, fontSize: '0.8rem' }}>
          The phone must stay docked while you enroll.
        </Typography>
        <Box sx={{ display: 'flex', justifyContent: 'center' }}>
          <Button onClick={onClose} sx={{ color: t.textMuted }}>
            Done
          </Button>
        </Box>
      </Box>
    </Modal>
  )
}
