// [hub] One phone in the presence row: a person, not a device (D6). Shows the
// person's name/colour, a presence ring, and (when LIVI shares it) battery.
// Glanceable at a distance; deliberately not interactive-looking beyond a tap.
//
// [hub] (work-log 31): redesigned again for more visual impact —
// conic-gradient presence ring, phone icon overlay, frosted glass avatar,
// drop shadow with colour glow, and a refined battery badge.
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
  absent: 'rgba(120,120,130,0.25)',
  nearby: 'rgba(180,180,190,0.4)',
  present: 'rgba(100,200,130,0.55)',
  docked: 'rgba(100,180,230,0.65)',
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
  const colour = phone.person?.colour || '#7A6F9B'
  const level = phone.presence?.level ?? 'absent'
  const ringColor = PRESENCE_RING_COLOR[level] ?? PRESENCE_RING_COLOR.absent
  const dimmed = level === 'absent'
  const battery = phone.livi?.batteryLevel
  const charging = phone.livi?.batteryCharging
  const initial = (hasRealName ? rawName! : (deviceName || '?')).trim().charAt(0).toUpperCase() || '?'
  const isProjecting = level === 'projecting'
  const isDocked = level === 'docked' || level === 'projecting'
  const large = size === 'large'

  // Sizes — fluid, responsive to viewport (§12.1)
  const avatarSize = large ? 'clamp(4.5rem, 14vmin, 7rem)' : 'clamp(3.5rem, 10vmin, 5rem)'
  const ringWidth = large ? '4px' : '3px'

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
        gap: large ? '0.5rem' : '0.4rem',
        minWidth: large ? '6.5rem' : '5rem',
        padding: large ? '0.7rem' : '0.5rem',
        opacity: dimmed ? 0.4 : 1,
        cursor: onSelect ? 'pointer' : 'default',
        transition: 'opacity 300ms ease, transform 200ms cubic-bezier(0.16,1,0.3,1)',
        '&:hover': onSelect ? { transform: 'scale(1.08)', opacity: dimmed ? 0.6 : 1 } : {},
        '&:active': onSelect ? { transform: 'scale(0.95)' } : {}
      }}
    >
      {/* [hub] Avatar with presence ring — layered for depth */}
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
        {/* [hub] Outer glow — soft coloured shadow for depth */}
        <Box
          sx={{
            position: 'absolute',
            inset: '-2px',
            borderRadius: '50%',
            background: `radial-gradient(circle at 50% 40%, ${colour}30 0%, transparent 70%)`,
            opacity: dimmed ? 0.3 : 1,
            transition: 'opacity 300ms ease',
            ...(isProjecting ? {
              animation: 'hub-bubble-glow 2.5s ease-in-out infinite'
            } : {})
          }}
        />
        {/* [hub] Presence ring — conic gradient for a modern look */}
        <Box
          sx={{
            position: 'absolute',
            inset: 0,
            borderRadius: '50%',
            padding: ringWidth,
            background: dimmed
              ? ringColor
              : `conic-gradient(from 135deg, ${ringColor}, ${colour}88, ${ringColor})`,
            transition: 'background 400ms ease',
            ...(isProjecting ? {
              animation: 'hub-bubble-ring-rotate 4s linear infinite'
            } : {})
          }}
        >
          <Box
            sx={{
              width: '100%',
              height: '100%',
              borderRadius: '50%',
              background: t.bg || '#1a1a2e'
            }}
          />
        </Box>
        {/* [hub] Avatar circle — frosted glass with gradient */}
        <Box
          sx={{
            position: 'relative',
            width: `calc(100% - ${ringWidth} * 2)`,
            height: `calc(100% - ${ringWidth} * 2)`,
            borderRadius: '50%',
            background: `linear-gradient(135deg, ${colour} 0%, ${colour}cc 60%, ${colour}99 100%)`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            fontWeight: 700,
            // [hub] Frosted glass effect — inset highlight + shadow for depth
            boxShadow: `
              inset 0 2px 4px rgba(255,255,255,0.3),
              inset 0 -2px 6px rgba(0,0,0,0.2),
              0 4px 16px rgba(0,0,0,0.3),
              0 1px 3px rgba(0,0,0,0.15)
            `,
            ...(isProjecting ? {
              boxShadow: `
                inset 0 2px 4px rgba(255,255,255,0.35),
                inset 0 -2px 6px rgba(0,0,0,0.2),
                0 0 1.5rem ${colour}55,
                0 4px 16px rgba(0,0,0,0.3)
              `
            } : {}),
            transition: 'box-shadow 400ms ease'
          }}
        >
          <Typography
            component="span"
            sx={{
              fontSize: large ? 'clamp(1.6rem, 5vmin, 2.6rem)' : 'clamp(1.2rem, 4vmin, 1.8rem)',
              fontWeight: 700,
              textShadow: '0 1px 3px rgba(0,0,0,0.3)',
              userSelect: 'none',
              letterSpacing: '-0.02em'
            }}
          >
            {initial}
          </Typography>
        </Box>
        {/* [hub] Battery badge — bottom-right, frosted pill */}
        {typeof battery === 'number' && large && (
          <Box
            sx={{
              position: 'absolute',
              bottom: '-3px',
              right: '-3px',
              backgroundColor: t.surface || 'rgba(30,30,50,0.95)',
              border: `2px solid ${t.bg || '#1a1a2e'}`,
              borderRadius: '12px',
              padding: '0.1rem 0.4rem',
              fontSize: 'clamp(0.55rem, 1.6vmin, 0.75rem)',
              fontWeight: 700,
              color: battery < 20 ? '#ef5350' : battery < 40 ? '#ffa726' : '#66bb6a',
              lineHeight: 1.2,
              display: 'flex',
              alignItems: 'center',
              gap: '0.1rem',
              whiteSpace: 'nowrap',
              boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
              backdropFilter: 'blur(4px)',
              WebkitBackdropFilter: 'blur(4px)'
            }}
          >
            {charging && <span style={{ fontSize: '0.85em' }}>⚡</span>}
            {battery}%
          </Box>
        )}
        {/* [hub] Docked indicator — small dot at top-right when docked */}
        {isDocked && !isProjecting && large && (
          <Box
            sx={{
              position: 'absolute',
              top: '-1px',
              right: '2px',
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: '#64b5f6',
              border: `1.5px solid ${t.bg || '#1a1a2e'}`,
              boxShadow: '0 0 6px rgba(100,181,246,0.6)'
            }}
          />
        )}
      </Box>

      {/* [hub] Name + presence label */}
      <Typography
        component="span"
        sx={{
          color: needsNaming ? t.textMuted : t.text,
          fontSize: large ? 'clamp(1rem, 3.2vmin, 1.4rem)' : 'clamp(0.85rem, 2.5vmin, 1.1rem)',
          lineHeight: 1.1,
          fontWeight: large ? 600 : 500,
          textAlign: 'center',
          userSelect: 'none',
          ...(needsNaming ? { fontStyle: 'italic', opacity: 0.7 } : {})
        }}
      >
        {needsNaming ? 'Name this phone' : displayName}
      </Typography>
      <Typography
        component="span"
        sx={{
          color: t.textMuted,
          fontSize: large ? 'clamp(0.7rem, 1.8vmin, 0.9rem)' : 'clamp(0.6rem, 1.6vmin, 0.8rem)',
          lineHeight: 1,
          textAlign: 'center',
          userSelect: 'none',
          opacity: 0.7
        }}
      >
        {PRESENCE_LABEL[level] ?? level}
        {typeof battery === 'number' && !large ? ` · ${battery}%` : ''}
      </Typography>

      {/* [hub] Keyframes for projecting animations */}
      <style>{`
        @keyframes hub-bubble-glow {
          0%, 100% { opacity: 0.6 }
          50% { opacity: 1 }
        }
        @keyframes hub-bubble-ring-rotate {
          from { transform: rotate(0deg) }
          to { transform: rotate(360deg) }
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
