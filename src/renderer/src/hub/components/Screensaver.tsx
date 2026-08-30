// [hub] The Home screen (formerly "screensaver"). Glanceable by default: a calm
// clock and date, nothing that scrolls or rewards attention (§2.2.1). In Phase
// 3.6 this also hides the GPU video plane via setVisible(false); here it is just
// the ambient face.
// [hub] Phase 1.10: shows phone bubbles above the clock when phones are present.
// [hub] Phase 5 (work-log 44): when now-playing data is provided, the screen
// splits — top half shows clock/bubbles/status, bottom half shows the
// NowPlaying split variant. Phone bubbles remain tappable to switch phones.
// [hub] Work-log 48: the split layout was too visually heavy. Replaced with an
// "ambient strip" design.
// [hub] Work-log 48 rev 2: use the same compact NowPlaying variant as the
// landing page bar — uniform look across screens. Wrapped in a floating card
// with margin from the bottom edge so it reads as a tappable widget, not a
// footer. Transport buttons (prev/play/next) work directly; tapping the
// thumbnail or title area expands to the full NowPlaying overlay.
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
  /** When provided, a compact now-playing card appears near the bottom */
  nowPlaying?: NowPlayingData
  /** Phone name for the now-playing source label */
  phoneLabel?: string
  /** Tap the now-playing card to expand the full NowPlaying overlay */
  onExpandNowPlaying?: () => void
}

export function Screensaver({ message, subtitle, phones, onSelect, nowPlaying, phoneLabel, onExpandNowPlaying }: ScreensaverProps) {
  const t = useHubTokens()
  const now = useClock()
  const time = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  const date = now.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' })

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
      {/* Main area — centered clock/bubbles (always, whether or not music is playing) */}
      <Box
        sx={{
          flex: '1 1 auto',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '0.5rem'
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

      {/* Compact now-playing card — same variant as the landing page bar.
          Floating card with margin from the bottom edge, rounded corners,
          subtle border + shadow so it reads as a tappable widget. Transport
          buttons work directly (play/pause/prev/next). Tapping the thumbnail
          or title area expands to the full NowPlaying overlay. */}
      {nowPlaying && (
        <Box
          data-testid="hub-now-playing-strip"
          sx={{
            flexShrink: 0,
            margin: '0 clamp(0.75rem, 3vw, 1.5rem) clamp(1rem, 3vh, 2rem)',
            padding: 'clamp(0.6rem, 2vh, 1rem) clamp(0.75rem, 2.5vw, 1.25rem)',
            borderRadius: 'clamp(12px, 2.5vw, 18px)',
            backgroundColor: t.surface,
            border: `1px solid ${t.border}`,
            boxShadow: '0 4px 20px rgba(0,0,0,0.25)',
            cursor: 'pointer',
            transition: 'transform 100ms ease, box-shadow 160ms ease, background-color 160ms ease',
            '&:active': { transform: 'scale(0.98)' },
            '&:hover': { boxShadow: '0 6px 28px rgba(0,0,0,0.35)', backgroundColor: t.surfaceMuted }
          }}
          onClick={onExpandNowPlaying}
          role="button"
          tabIndex={0}
          aria-label={`Now playing: ${nowPlaying.title || 'Unknown track'} by ${nowPlaying.artist || 'Unknown artist'}. Tap to expand.`}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onExpandNowPlaying?.() }}
        >
          {/* Compact NowPlaying — same component as the landing page bar.
              Transport buttons call stopPropagation internally so tapping
              play/pause/prev/next doesn't trigger the card expand. Tapping
              anywhere else on the card (thumbnail, title, artist) expands. */}
          <NowPlaying data={nowPlaying} variant="compact" phoneLabel={phoneLabel} />
        </Box>
      )}
    </Box>
  )
}
