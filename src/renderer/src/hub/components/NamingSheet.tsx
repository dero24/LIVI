// [hub] G2 / §6.2 — the naming sheet. The phone is fully functional before it
// is named; naming is an invitation, not a gate. This sheet opens from the
// "Whose phone is this?" chip, takes a name once, and posts phone.rename.
// Also offers the per-phone "don't auto-take the screen" toggle (R1) and, when
// the phone has no companion, the "also reach this phone when it's not docked"
// line that opens EnrolSheet.
import { Box, Button, Modal, Switch, TextField, Typography } from '@mui/material'
import { useState } from 'react'
import type { HubPhone } from '../types'
import { useHubTokens } from '../useHubTokens'
import { EnrolSheet } from './EnrolSheet'

export interface NamingSheetProps {
  phone: HubPhone
  open: boolean
  onClose: () => void
  onRename: (phoneId: string, name: string) => void
  onSetAutoDock?: (phoneId: string, autoDock: boolean) => void
  onEnrolStart?: (phoneId: string) => void
}

export function NamingSheet({
  phone,
  open,
  onClose,
  onRename,
  onSetAutoDock,
  onEnrolStart
}: NamingSheetProps) {
  const t = useHubTokens()
  const [name, setName] = useState(phone.person?.name ?? '')
  const [autoDock, setAutoDock] = useState(phone.policy?.autoDock !== false)
  const [enrolOpen, setEnrolOpen] = useState(false)

  const hasCompanion = Boolean(phone.companion)
  const model = phone.person?.name ?? 'this phone'

  const save = () => {
    const trimmed = name.trim()
    if (trimmed) onRename(phone.phoneId, trimmed)
    onSetAutoDock?.(phone.phoneId, autoDock)
    onClose()
  }

  return (
    <>
      <Modal open={open && !enrolOpen} onClose={onClose} aria-label="Name this phone">
        <Box
          data-testid="hub-naming-sheet"
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
            gap: '1rem'
          }}
        >
          <Typography sx={{ fontSize: 'clamp(1.2rem, 5vmin, 1.8rem)', fontWeight: 600 }}>
            Whose phone is this?
          </Typography>
          <Typography sx={{ color: t.textMuted, fontSize: 'clamp(0.85rem, 3vmin, 1rem)' }}>
            {model} · name it once so the hub can tell it apart.
          </Typography>
          <TextField
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Sarah"
            slotProps={{ htmlInput: { 'data-testid': 'hub-naming-input', maxLength: 40 } }}
            sx={{ '& .MuiInputBase-input': { color: t.text } }}
          />
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Box>
              <Typography sx={{ fontSize: '0.95rem' }}>Auto-take the screen when docked</Typography>
              <Typography sx={{ color: t.textMuted, fontSize: '0.8rem' }}>
                Off = show a bubble, wait for a tap (good for shared phones)
              </Typography>
            </Box>
            <Switch
              checked={autoDock}
              onChange={(_, v) => setAutoDock(v)}
              data-testid="hub-naming-autodock"
            />
          </Box>
          {!hasCompanion && (
            <Button
              variant="text"
              sx={{ color: t.ring, textTransform: 'none', alignSelf: 'flex-start' }}
              onClick={() => setEnrolOpen(true)}
              data-testid="hub-naming-enrol-offer"
            >
              Also reach this phone when it's not docked →
            </Button>
          )}
          <Box sx={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
            <Button onClick={onClose} sx={{ color: t.textMuted }}>
              Later
            </Button>
            <Button
              variant="contained"
              onClick={save}
              disabled={!name.trim()}
              data-testid="hub-naming-save"
            >
              Save
            </Button>
          </Box>
        </Box>
      </Modal>

      <EnrolSheet
        phone={phone}
        open={enrolOpen}
        onClose={() => setEnrolOpen(false)}
        onEnrolStart={onEnrolStart}
      />
    </>
  )
}
