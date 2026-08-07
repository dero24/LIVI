// [hub] G2 / §6.2 — the dismissible "Whose phone is this?" chip. Shown once
// per unnamed phone (person.name unset or still the model default) and per
// phone with no companion. Tapping opens the NamingSheet. Dismissable forever
// per phone — naming is an invitation, not a gate.
import { Box, Chip } from '@mui/material'
import { useState } from 'react'
import type { HubPhone } from '../types'
import { useHubTokens } from '../useHubTokens'
import { NamingSheet } from './NamingSheet'

export interface FirstRunChipProps {
  phone: HubPhone
  onRename: (phoneId: string, name: string) => void
  onSetAutoDock?: (phoneId: string, autoDock: boolean) => void
  onEnrolStart?: (phoneId: string) => Promise<{ code?: string } | void> | void
}

// Heuristic: a phone is "unnamed" if person.name is missing or matches the
// model default pattern (a single token like "Pixel 8"). The hub is the
// authority, but this avoids a flicker on first dock.
function isUnnamed(p: HubPhone): boolean {
  const name = p.person?.name
  if (!name) return true
  // A person's name usually has a capitalised first word and no digits; a model
  // name often has digits (Pixel 8, SM-S908U) or all-caps tokens.
  return /\d/.test(name) || /^[A-Z]{2,}/.test(name)
}

export function FirstRunChip({ phone, onRename, onSetAutoDock, onEnrolStart }: FirstRunChipProps) {
  const t = useHubTokens()
  const [dismissed, setDismissed] = useState(false)
  const [sheetOpen, setSheetOpen] = useState(false)

  if (dismissed) return null
  // Show the chip if the phone is unnamed OR has no companion (enrol offer).
  const needsName = isUnnamed(phone)
  const needsEnrol = !phone.companion
  if (!needsName && !needsEnrol) return null

  const label = needsName ? 'Whose phone is this?' : 'Also reach this phone when not docked'

  return (
    <>
      <Box
        sx={{
          position: 'absolute',
          top: '0.6rem',
          left: '50%',
          transform: 'translateX(-50%)',
          zIndex: 3
        }}
      >
        <Chip
          label={label}
          onClick={() => setSheetOpen(true)}
          onDelete={() => setDismissed(true)}
          data-testid="hub-firstrun-chip"
          sx={{
            backgroundColor: t.surfaceMuted,
            color: t.text,
            border: `1px solid ${t.border}`,
            '& .MuiChip-deleteIcon': { color: t.textMuted }
          }}
        />
      </Box>
      <NamingSheet
        phone={phone}
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        onRename={onRename}
        onSetAutoDock={onSetAutoDock}
        onEnrolStart={onEnrolStart}
      />
    </>
  )
}
