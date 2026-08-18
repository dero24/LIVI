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

// Heuristic: a phone is "unnamed" if person.name is missing, empty, or matches
// a generic device/platform name. The hub authority (registry.py) now stores
// LIVI's device model as person.deviceName, not person.name, so person.name
// should be null until the user names it. This check is a safety net for any
// pre-existing records that still have a device name in person.name.
const GENERIC_NAMES = new Set([
  'android', 'phone', 'device', 'unknown', 'carplay', 'ios'
])
function isUnnamed(p: HubPhone): boolean {
  const name = p.person?.name
  if (!name || !name.trim()) return true
  if (GENERIC_NAMES.has(name.trim().toLowerCase())) return true
  // Model numbers: SM-S908U, Pixel 8, iPhone 15 Pro — has digits or all-caps
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
