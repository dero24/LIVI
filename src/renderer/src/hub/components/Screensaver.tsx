// [hub] The idle surface. Glanceable by default: a calm clock and date, nothing
// that scrolls or rewards attention (§2.2.1). In Phase 3.6 this also hides the
// GPU video plane via setVisible(false); here it is just the ambient face.
// [hub] Phase 1.10: shows phone bubbles above the clock when phones are present.
import { Box, Typography } from '@mui/material'
import { useEffect, useState } from 'react'
import type { HubPhone } from '../types'
import { useHubTokens } from '../useHubTokens'
import { PresenceRow } from './PresenceRow'

function useClock(): Date {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 10_000)
    return () => clearInterval(id)
  }, [])
  return now
}

export interface ScreensaverProps {
  message?: string
  subtitle?: string
  phones?: HubPhone[]
  onSelect?: (phoneId: string) => void
}

export function Screensaver({ message, subtitle, phones, onSelect }: ScreensaverProps) {
  const t = useHubTokens()
  const now = useClock()
  const time = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  const date = now.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' })
  return (
    <Box
      data-testid="hub-screensaver"
      sx={{
        position: 'absolute',
        inset: 0,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '0.5rem',
        backgroundColor: t.bg,
        color: t.text
      }}
    >
      {/* [hub] Phase 1.10: phone bubbles above the clock — larger, more visual */}
      {phones && phones.length > 0 && (
        <PresenceRow
          phones={phones}
          onSelect={onSelect}
          size="large"
          sx={{
            backgroundColor: 'transparent',
            borderBottom: 'none',
            padding: 'clamp(1rem, 3vh, 2rem) 0',
          }}
        />
      )}
      <Typography sx={{ fontSize: 'clamp(3rem, 18vmin, 9rem)', fontWeight: 300, lineHeight: 1 }}>
        {time}
      </Typography>
      <Typography sx={{ fontSize: 'clamp(1rem, 4vmin, 2rem)', color: t.textMuted }}>
        {date}
      </Typography>
      {subtitle ? (
        <Typography
          sx={{ mt: '0.5rem', fontSize: 'clamp(0.9rem, 3vmin, 1.4rem)', color: t.textMuted, textAlign: 'center' }}
        >
          {subtitle}
        </Typography>
      ) : null}
      {message ? (
        <Typography
          sx={{ mt: '1rem', fontSize: 'clamp(0.9rem, 3vmin, 1.4rem)', color: t.textMuted }}
        >
          {message}
        </Typography>
      ) : null}
    </Box>
  )
}
