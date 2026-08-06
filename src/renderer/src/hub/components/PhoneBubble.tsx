// [hub] One phone in the presence row: a person, not a device (D6). Shows the
// person's name/colour, a presence ring, and (when LIVI shares it) battery.
// Glanceable at a distance; deliberately not interactive-looking beyond a tap.
import { Box, Typography } from '@mui/material'
import type { HubPhone } from '../types'
import { useHubTokens } from '../useHubTokens'

const PRESENCE_LABEL: Record<string, string> = {
  absent: 'Away',
  nearby: 'Nearby',
  present: 'Home',
  docked: 'Docked',
  projecting: 'On screen'
}

export interface PhoneBubbleProps {
  phone: HubPhone
  onSelect?: (phoneId: string) => void
}

export function PhoneBubble({ phone, onSelect }: PhoneBubbleProps) {
  const t = useHubTokens()
  const name = phone.person?.name || 'Phone'
  const colour = phone.person?.colour || t.ring
  const level = phone.presence?.level ?? 'absent'
  const ring = t.presence[level] ?? t.presence.absent
  const dimmed = level === 'absent'
  const battery = phone.livi?.batteryLevel
  const initial = name.trim().charAt(0).toUpperCase() || '?'

  return (
    <Box
      role={onSelect ? 'button' : undefined}
      aria-label={`${name}, ${PRESENCE_LABEL[level] ?? level}`}
      data-testid="hub-phone-bubble"
      data-phone-id={phone.phoneId}
      onClick={onSelect ? () => onSelect(phone.phoneId) : undefined}
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '0.35rem',
        // Touch target in physical units, not pixels (§11.5).
        minWidth: '4.5rem',
        padding: '0.5rem',
        opacity: dimmed ? 0.5 : 1,
        cursor: onSelect ? 'pointer' : 'default',
        transition: 'opacity 300ms ease'
      }}
    >
      <Box
        sx={{
          position: 'relative',
          width: 'clamp(2.75rem, 8vmin, 4rem)',
          height: 'clamp(2.75rem, 8vmin, 4rem)',
          borderRadius: '50%',
          backgroundColor: colour,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#fff',
          fontWeight: 600,
          boxShadow: `0 0 0 0.2rem ${ring}`
        }}
      >
        <Typography component="span" sx={{ fontSize: 'clamp(1.1rem, 3.5vmin, 1.6rem)' }}>
          {initial}
        </Typography>
      </Box>
      <Typography
        component="span"
        sx={{ color: t.text, fontSize: 'clamp(0.8rem, 2.2vmin, 1rem)', lineHeight: 1.1 }}
      >
        {name}
      </Typography>
      <Typography
        component="span"
        sx={{ color: t.textMuted, fontSize: 'clamp(0.65rem, 1.8vmin, 0.85rem)', lineHeight: 1 }}
      >
        {PRESENCE_LABEL[level] ?? level}
        {typeof battery === 'number' ? ` · ${battery}%` : ''}
      </Typography>
    </Box>
  )
}
