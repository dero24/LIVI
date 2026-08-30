// [hub] The Home screen (formerly "screensaver"). Glanceable by default: a calm
// clock and date, nothing that scrolls or rewards attention (§2.2.1). In Phase
// 3.6 this also hides the GPU video plane via setVisible(false); here it is just
// the ambient face.
// [hub] Phase 1.10: shows phone bubbles above the clock when phones are present.
// [hub] Phase 5 (work-log 44): when now-playing data is provided, the screen
// splits — top half shows clock/bubbles/status, bottom half shows the
// NowPlaying split variant. Phone bubbles remain tappable to switch phones.
import { Box, Typography } from '@mui/material'
import { useEffect, useState } from 'react'
import type { HubPhone } from '../types'
import { useHubTokens } from '../useHubTokens'
import type { NowPlayingData } from '../useNowPlaying'
import { NowPlaying } from './NowPlaying'
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
  /** When provided, the screen splits: top=clock+bubbles, bottom=now-playing */
  nowPlaying?: NowPlayingData
  /** Phone name for the now-playing source label */
  phoneLabel?: string
}

export function Screensaver({ message, subtitle, phones, onSelect, nowPlaying, phoneLabel }: ScreensaverProps) {
  const t = useHubTokens()
  const now = useClock()
  const time = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  const date = now.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' })

  // Split mode: top half = clock/bubbles/status, bottom half = now-playing
  if (nowPlaying) {
    return (
      <Box
        data-testid="hub-home"
        sx={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          backgroundColor: t.bg,
          color: t.text,
          overflow: 'hidden'
        }}
      >
        {/* Top half — clock, bubbles, status */}
        <Box
          sx={{
            flex: '1 1 50%',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '0.4rem',
            padding: 'clamp(0.75rem, 2vh, 1.5rem) 0 0',
            overflow: 'hidden'
          }}
        >
          {phones && phones.length > 0 && (
            <PresenceRow
              phones={phones}
              onSelect={onSelect}
              size="large"
              sx={{
                backgroundColor: 'transparent',
                borderBottom: 'none',
                padding: 'clamp(0.5rem, 1.5vh, 1rem) 0'
              }}
            />
          )}
          <Typography sx={{ fontSize: 'clamp(2.5rem, 14vmin, 6rem)', fontWeight: 300, lineHeight: 1 }}>
            {time}
          </Typography>
          <Typography sx={{ fontSize: 'clamp(0.9rem, 3.5vmin, 1.6rem)', color: t.textMuted }}>
            {date}
          </Typography>
          {subtitle ? (
            <Typography
              sx={{ fontSize: 'clamp(0.8rem, 2.8vmin, 1.2rem)', color: t.textMuted, textAlign: 'center' }}
            >
              {subtitle}
            </Typography>
          ) : null}
        </Box>

        {/* Bottom half — now-playing */}
        <Box
          sx={{
            flex: '1 1 50%',
            position: 'relative',
            overflow: 'hidden'
          }}
        >
          <NowPlaying data={nowPlaying} variant="split" phoneLabel={phoneLabel} />
        </Box>
      </Box>
    )
  }

  // Default mode: centered clock/bubbles (no now-playing)
  return (
    <Box
      data-testid="hub-home"
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
