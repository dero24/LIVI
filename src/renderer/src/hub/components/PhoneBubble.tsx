// [hub] One phone in the presence row: a person, not a device (D6). Shows the
// person's name/colour, a presence ring, and (when LIVI shares it) battery.
// Glanceable at a distance; deliberately not interactive-looking beyond a tap.
//
// [hub] (work-log 30): redesigned with a modern, responsive UI —
// glassmorphism, smooth presence ring animation, battery pill, projecting
// glow, and a graceful fallback for unnamed phones ("Name this phone" prompt
// instead of showing the raw device model).
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

// [hub] Presence ring colours — soft, calm, not alarming.
const PRESENCE_RING_COLOR: Record<string, string> = {
  absent: 'rgba(120,120,130,0.3)',
  nearby: 'rgba(180,180,190,0.5)',
  present: 'rgba(120,200,140,0.6)',
  docked: 'rgba(120,180,220,0.7)',
  projecting: 'rgba(100,160,255,0.8)'
}

const GENERIC_NAMES = new Set([
  'android', 'phone', 'device', 'unknown', 'carplay', 'ios'
])
function isGenericName(name: string | null | undefined): boolean {
  if (!name || !name.trim()) return true
  return GENERIC_NAMES.has(name.trim().toLowerCase()) || /\d/.test(name) || /^[A-Z]{2,}/.test(name)
}

export interface PhoneBubbleProps {
  phone: HubPhone
  onSelect?: (phoneId: string) => void
  size?: 'default' | 'large'
}

export function PhoneBubble({ phone, onSelect, size = 'default' }: PhoneBubbleProps) {
  const t = useHubTokens()
  const rawName = phone.person?.name
  const deviceName = phone.person?.deviceName
  const hasRealName = !isGenericName(rawName)
  const displayName = hasRealName ? rawName! : (deviceName || 'New phone')
  const needsNaming = !hasRealName
  const colour = phone.person?.colour || t.ring
  const level = phone.presence?.level ?? 'absent'
  const ringColor = PRESENCE_RING_COLOR[level] ?? PRESENCE_RING_COLOR.absent
  const dimmed = level === 'absent'
  const battery = phone.livi?.batteryLevel
  const charging = phone.livi?.batteryCharging
  const initial = (hasRealName ? rawName! : (deviceName || '?')).trim().charAt(0).toUpperCase() || '?'
  const isProjecting = level === 'projecting'
  const large = size === 'large'

  // Sizes — fluid, responsive to viewport (§12.1)
  const avatarSize = large ? 'clamp(4rem, 13vmin, 6.5rem)' : 'clamp(2.75rem, 8vmin, 4rem)'
  const ringWidth = large ? '0.25rem' : '0.18rem'

  return (
    <Box
      role={onSelect ? 'button' : undefined}
      aria-label={`${displayName}, ${PRESENCE_LABEL[level] ?? level}`}
      data-testid="hub-phone-bubble"
      data-phone-id={phone.phoneId}
      onClick={onSelect ? () => onSelect(phone.phoneId) : undefined}
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: large ? '0.55rem' : '0.35rem',
        minWidth: large ? '6rem' : '4.5rem',
        padding: large ? '0.75rem' : '0.5rem',
        opacity: dimmed ? 0.45 : 1,
        cursor: onSelect ? 'pointer' : 'default',
        transition: 'opacity 300ms ease, transform 200ms cubic-bezier(0.16,1,0.3,1)',
        '&:hover': onSelect ? { transform: 'scale(1.06)', opacity: dimmed ? 0.6 : 1 } : {},
        '&:active': onSelect ? { transform: 'scale(0.97)' } : {}
      }}
    >
      <Box
        sx={{
          position: 'relative',
          width: avatarSize,
          height: avatarSize,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center'
        }}
      >
        {/* [hub] Presence ring — animated, soft glow */}
        <Box
          sx={{
            position: 'absolute',
            inset: 0,
            borderRadius: '50%',
            boxShadow: `0 0 0 ${ringWidth} ${ringColor}`,
            transition: 'box-shadow 400ms ease',
            ...(isProjecting ? {
              animation: 'hub-bubble-pulse 2.5s ease-in-out infinite'
            } : {})
          }}
        />
        {/* [hub] Avatar circle — gradient + glass effect */}
        <Box
          sx={{
            position: 'relative',
            width: '100%',
            height: '100%',
            borderRadius: '50%',
            background: `linear-gradient(145deg, ${colour} 0%, ${colour}dd 100%)`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            fontWeight: 600,
            // [hub] Subtle inner highlight for depth (glassmorphism)
            boxShadow: `inset 0 1px 2px rgba(255,255,255,0.25), inset 0 -1px 3px rgba(0,0,0,0.15), 0 4px 12px rgba(0,0,0,0.2)`,
            ...(isProjecting ? {
              boxShadow: `inset 0 1px 2px rgba(255,255,255,0.3), inset 0 -1px 3px rgba(0,0,0,0.15), 0 0 1.5rem 0.15rem ${colour}66`
            } : {}),
            transition: 'box-shadow 400ms ease'
          }}
        >
          <Typography
            component="span"
            sx={{
              fontSize: large ? 'clamp(1.6rem, 5vmin, 2.4rem)' : 'clamp(1.1rem, 3.5vmin, 1.6rem)',
              fontWeight: 600,
              textShadow: '0 1px 2px rgba(0,0,0,0.2)',
              userSelect: 'none'
            }}
          >
            {initial}
          </Typography>
        </Box>
        {/* [hub] Battery pill — bottom-right of avatar, only when we have data */}
        {typeof battery === 'number' && large && (
          <Box
            sx={{
              position: 'absolute',
              bottom: '-2px',
              right: '-2px',
              backgroundColor: t.surface,
              border: `1.5px solid ${t.border}`,
              borderRadius: '10px',
              padding: '0.1rem 0.35rem',
              fontSize: 'clamp(0.6rem, 1.8vmin, 0.8rem)',
              fontWeight: 600,
              color: battery < 20 ? '#e57373' : battery < 50 ? '#f0c04b' : '#81c784',
              lineHeight: 1,
              display: 'flex',
              alignItems: 'center',
              gap: '0.15rem',
              whiteSpace: 'nowrap',
              boxShadow: '0 2px 6px rgba(0,0,0,0.25)'
            }}
          >
            {charging && <span style={{ fontSize: '0.9em' }}>⚡</span>}
            {battery}%
          </Box>
        )}
      </Box>

      {/* [hub] Name + presence label */}
      <Typography
        component="span"
        sx={{
          color: needsNaming ? t.textMuted : t.text,
          fontSize: large ? 'clamp(1rem, 3vmin, 1.3rem)' : 'clamp(0.8rem, 2.2vmin, 1rem)',
          lineHeight: 1.1,
          fontWeight: large ? 500 : 400,
          textAlign: 'center',
          userSelect: 'none',
          ...(needsNaming ? { fontStyle: 'italic' } : {})
        }}
      >
        {needsNaming ? 'Name this phone' : displayName}
      </Typography>
      <Typography
        component="span"
        sx={{
          color: t.textMuted,
          fontSize: large ? 'clamp(0.75rem, 2vmin, 0.95rem)' : 'clamp(0.65rem, 1.8vmin, 0.85rem)',
          lineHeight: 1,
          textAlign: 'center',
          userSelect: 'none'
        }}
      >
        {PRESENCE_LABEL[level] ?? level}
        {typeof battery === 'number' && !large ? ` · ${battery}%` : ''}
      </Typography>

      {/* [hub] Keyframes for projecting pulse — soft, alive, not flashing */}
      <style>{`
        @keyframes hub-bubble-pulse {
          0%, 100% { box-shadow: 0 0 0 ${ringWidth} ${ringColor}, 0 0 0.5rem 0.1rem ${colour}44 }
          50% { box-shadow: 0 0 0 ${ringWidth} ${ringColor}, 0 0 1.5rem 0.2rem ${colour}66 }
        }
        @media (prefers-reduced-motion: reduce) {
          [data-testid="hub-phone-bubble"] * {
            animation: none !important;
          }
        }
      `}</style>
    </Box>
  )
}
