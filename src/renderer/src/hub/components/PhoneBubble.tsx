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
  size?: 'default' | 'large'
}

export function PhoneBubble({ phone, onSelect, size = 'default' }: PhoneBubbleProps) {
  const t = useHubTokens()
  const name = phone.person?.name || 'Phone'
  const colour = phone.person?.colour || t.ring
  const level = phone.presence?.level ?? 'absent'
  const ring = t.presence[level] ?? t.presence.absent
  const dimmed = level === 'absent'
  const battery = phone.livi?.batteryLevel
  const initial = name.trim().charAt(0).toUpperCase() || '?'
  const isProjecting = level === 'projecting'
  const large = size === 'large'

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
        gap: large ? '0.5rem' : '0.35rem',
        // Touch target in physical units, not pixels (§11.5).
        minWidth: large ? '6rem' : '4.5rem',
        padding: large ? '0.75rem' : '0.5rem',
        opacity: dimmed ? 0.5 : 1,
        cursor: onSelect ? 'pointer' : 'default',
        transition: 'opacity 300ms ease, transform 200ms ease',
        '&:hover': onSelect ? { transform: 'scale(1.05)' } : {}
      }}
    >
      <Box
        sx={{
          position: 'relative',
          width: large ? 'clamp(4rem, 12vmin, 6rem)' : 'clamp(2.75rem, 8vmin, 4rem)',
          height: large ? 'clamp(4rem, 12vmin, 6rem)' : 'clamp(2.75rem, 8vmin, 4rem)',
          borderRadius: '50%',
          backgroundColor: colour,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#fff',
          fontWeight: 600,
          boxShadow: `0 0 0 ${large ? '0.3rem' : '0.2rem'} ${ring}`,
          // [hub] Phase 1.10: subtle glow for projecting phones in large mode
          ...(large && isProjecting ? {
            boxShadow: `0 0 0 0.3rem ${ring}, 0 0 1.5rem 0.2rem ${colour}80`
          } : {})
        }}
      >
        <Typography component="span" sx={{ fontSize: large ? 'clamp(1.6rem, 5vmin, 2.4rem)' : 'clamp(1.1rem, 3.5vmin, 1.6rem)' }}>
          {initial}
        </Typography>
      </Box>
      <Typography
        component="span"
        sx={{ color: t.text, fontSize: large ? 'clamp(1rem, 3vmin, 1.3rem)' : 'clamp(0.8rem, 2.2vmin, 1rem)', lineHeight: 1.1, fontWeight: large ? 500 : 400 }}
      >
        {name}
      </Typography>
      <Typography
        component="span"
        sx={{ color: t.textMuted, fontSize: large ? 'clamp(0.8rem, 2.2vmin, 1rem)' : 'clamp(0.65rem, 1.8vmin, 0.85rem)', lineHeight: 1 }}
      >
        {PRESENCE_LABEL[level] ?? level}
        {typeof battery === 'number' ? ` · ${battery}%` : ''}
      </Typography>
    </Box>
  )
}
