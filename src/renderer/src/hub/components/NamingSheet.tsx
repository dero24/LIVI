// [hub] G2 / §6.2 — the naming sheet. The phone is fully functional before it
// is named; naming is an invitation, not a gate. This sheet opens automatically
// when a phone has no name, takes a name once, and posts phone.rename.
// When the phone has no companion, it also offers the "also reach this phone
// when it's not docked" line that opens EnrolSheet.
import { Box, Button, Modal, TextField, Typography } from '@mui/material'
import { useState } from 'react'
import type { HubPhone } from '../types'
import { useHubTokens } from '../useHubTokens'
import { EnrolSheet } from './EnrolSheet'
import { TouchKeyboard } from './TouchKeyboard'

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
  onEnrolStart
}: NamingSheetProps) {
  const t = useHubTokens()
  const [name, setName] = useState('')
  const [enrolOpen, setEnrolOpen] = useState(false)

  const hasCompanion = Boolean(phone.companion)
  const model = phone.person?.deviceName ?? phone.person?.name ?? 'this phone'

  const save = () => {
    const trimmed = name.trim()
    if (trimmed) onRename(phone.phoneId, trimmed)
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
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Tap letters to type a name"
            slotProps={{ htmlInput: { 'data-testid': 'hub-naming-input', maxLength: 40 } }}
            sx={{
              '& .MuiInputBase-input': { color: t.text, fontSize: '1.2rem', textAlign: 'center' },
              '& .MuiOutlinedInput-root': {
                backgroundColor: t.surfaceMuted,
                '& fieldset': { borderColor: t.border }
              }
            }}
            inputRef={(el) => { if (el && open) el.blur() }}
          />
          <TouchKeyboard
            onKey={(ch) => setName((prev) => prev + ch)}
            onBackspace={() => setName((prev) => prev.slice(0, -1))}
            onEnter={save}
          />
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
