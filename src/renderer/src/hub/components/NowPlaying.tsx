// [hub] Phase 5: NowPlaying — premium now-playing display for the hub surface.
//
// Two variants:
//   - "full"    — ambient full-screen display for screensaver mode (album art
//                 hero, blurred background, metadata, progress bar, transport)
//   - "compact" — horizontal strip for the landing/aa bar (art thumbnail +
//                 title/artist + transport buttons)
//
// Design references (PRODUCT_ROADMAP.md §4 UX patterns):
//   - Spotify: dark-first, color-disciplined, one accent
//   - Apple Music: full-bleed art-driven background
//   - Nest Hub: low-density, high-contrast, tappable from a distance
//
// Touch targets: Play/Pause 80px, Prev/Next 56px (full) / 40px (compact)
// Progress bar: 6px track, 20px thumb, 48px invisible touch target
// Typography: title 36px/700, artist 26px/500, album 20px/400

import { Box, Typography, Slider } from '@mui/material'
import PlayArrowIcon from '@mui/icons-material/PlayArrowRounded'
import PauseIcon from '@mui/icons-material/PauseRounded'
import SkipNextIcon from '@mui/icons-material/SkipNextRounded'
import SkipPreviousIcon from '@mui/icons-material/SkipPreviousRounded'
import MusicNoteIcon from '@mui/icons-material/MusicNoteRounded'
import { useCallback } from 'react'
import type { ReactNode } from 'react'
import { useHubTokens } from '../useHubTokens'
import type { NowPlayingData } from '../useNowPlaying'

function formatTime(ms: number): string {
  if (!ms || ms < 0) return '0:00'
  const totalSec = Math.floor(ms / 1000)
  const min = Math.floor(totalSec / 60)
  const sec = totalSec % 60
  return `${min}:${sec.toString().padStart(2, '0')}`
}

interface NowPlayingProps {
  data: NowPlayingData
  variant: 'full' | 'compact' | 'split'
  /** Optional: phone name for the source label (e.g. "Bob's S22") */
  phoneLabel?: string
}

export function NowPlaying({ data, variant, phoneLabel }: NowPlayingProps) {
  const t = useHubTokens()

  if (variant === 'compact') {
    return <NowPlayingCompact data={data} phoneLabel={phoneLabel} />
  }
  if (variant === 'split') {
    return <NowPlayingSplit data={data} phoneLabel={phoneLabel} />
  }
  return <NowPlayingFull data={data} phoneLabel={phoneLabel} />
}

// ─── Full variant (screensaver ambient display) ──────────────────────────────

function NowPlayingFull({ data, phoneLabel }: { data: NowPlayingData; phoneLabel?: string }) {
  const t = useHubTokens()
  const pct = data.durationMs > 0 ? (data.elapsedMs / data.durationMs) * 100 : 0
  const sourceLabel = [data.appName, phoneLabel].filter(Boolean).join(' · ')

  return (
    <Box
      data-testid="hub-now-playing"
      sx={{
        position: 'absolute',
        inset: 0,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        overflow: 'hidden',
        // Blurred album art background — the "atmosphere" layer
        backgroundColor: '#0E1116',
        '&::before': data.artworkUrl
          ? {
              content: '""',
              position: 'absolute',
              inset: '-20%',
              backgroundImage: `url(${data.artworkUrl})`,
              backgroundSize: 'cover',
              backgroundPosition: 'center',
              filter: 'blur(70px) saturate(140%) brightness(0.45)',
              zIndex: 0
            }
          : undefined,
        // Dark vignette overlay for text legibility
        '&::after': {
          content: '""',
          position: 'absolute',
          inset: 0,
          background: 'linear-gradient(to bottom, rgba(14,17,22,0.55) 0%, rgba(14,17,22,0.75) 100%)',
          zIndex: 1
        }
      }}
    >
      {/* Content layer (above blurred bg + vignette) */}
      <Box
        sx={{
          position: 'relative',
          zIndex: 2,
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          padding: 'clamp(2rem, 6vh, 3.5rem) clamp(1.5rem, 5vw, 2.5rem) clamp(1.5rem, 4vh, 2.5rem)',
          gap: 'clamp(1rem, 2.5vh, 1.75rem)'
        }}
      >
        {/* Album art — the hero element */}
        <Box
          sx={{
            width: 'clamp(280px, 78vw, 480px)',
            aspectRatio: '1 / 1',
            borderRadius: 'clamp(12px, 2.5vw, 20px)',
            overflow: 'hidden',
            flexShrink: 0,
            boxShadow: '0 12px 40px rgba(0,0,0,0.5)',
            backgroundColor: 'rgba(255,255,255,0.06)',
            backgroundImage: data.artworkUrl ? `url(${data.artworkUrl})` : undefined,
            backgroundSize: 'cover',
            backgroundPosition: 'center',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            animation: 'hub-np-art-in 400ms ease-out',
            '@keyframes hub-np-art-in': {
              from: { opacity: 0, transform: 'scale(0.96)' },
              to: { opacity: 1, transform: 'scale(1)' }
            }
          }}
        >
          {!data.artworkUrl && (
            <MusicNoteIcon sx={{ fontSize: 'clamp(3rem, 12vw, 5rem)', color: 'rgba(255,255,255,0.25)' }} />
          )}
        </Box>

        {/* Metadata stack */}
        <Box
          sx={{
            width: '100%',
            maxWidth: '480px',
            textAlign: 'center',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.15rem',
            flexShrink: 0
          }}
        >
          <Typography
            sx={{
              fontSize: 'clamp(1.4rem, 5.5vmin, 2.1rem)',
              fontWeight: 700,
              color: '#FFFFFF',
              lineHeight: 1.15,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              textShadow: '0 2px 12px rgba(0,0,0,0.4)'
            }}
          >
            {data.title || 'Unknown track'}
          </Typography>
          <Typography
            sx={{
              fontSize: 'clamp(1rem, 4vmin, 1.4rem)',
              fontWeight: 500,
              color: 'rgba(255,255,255,0.72)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap'
            }}
          >
            {data.artist || 'Unknown artist'}
          </Typography>
          {data.album && data.album !== '-' && (
            <Typography
              sx={{
                fontSize: 'clamp(0.85rem, 3.2vmin, 1.1rem)',
                fontWeight: 400,
                color: 'rgba(255,255,255,0.5)',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap'
              }}
            >
              {data.album}
            </Typography>
          )}
          {sourceLabel && (
            <Typography
              sx={{
                fontSize: 'clamp(0.75rem, 2.8vmin, 0.95rem)',
                fontWeight: 500,
                color: 'rgba(255,255,255,0.4)',
                marginTop: '0.35rem',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap'
              }}
            >
              {sourceLabel}
            </Typography>
          )}
        </Box>

        {/* Progress bar */}
        <Box
          sx={{
            width: '100%',
            maxWidth: '480px',
            flexShrink: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: '0.3rem'
          }}
        >
          <Box
            sx={{
              width: '100%',
              height: '6px',
              borderRadius: '3px',
              backgroundColor: 'rgba(255,255,255,0.18)',
              overflow: 'hidden',
              position: 'relative'
            }}
          >
            <Box
              sx={{
                position: 'absolute',
                left: 0,
                top: 0,
                bottom: 0,
                width: `${pct}%`,
                backgroundColor: '#FFFFFF',
                borderRadius: '3px',
                transition: 'width 250ms linear'
              }}
            />
          </Box>
          <Box
            sx={{
              display: 'flex',
              justifyContent: 'space-between',
              width: '100%'
            }}
          >
            <Typography
              sx={{
                fontSize: 'clamp(0.7rem, 2.5vmin, 0.85rem)',
                fontWeight: 500,
                color: 'rgba(255,255,255,0.6)'
              }}
            >
              {formatTime(data.elapsedMs)}
            </Typography>
            <Typography
              sx={{
                fontSize: 'clamp(0.7rem, 2.5vmin, 0.85rem)',
                fontWeight: 500,
                color: 'rgba(255,255,255,0.6)'
              }}
            >
              {formatTime(data.durationMs)}
            </Typography>
          </Box>
        </Box>

        {/* Transport controls */}
        <TransportControls
          isPlaying={data.isPlaying}
          size="large"
          sx={{ marginTop: 'auto', paddingBottom: '0.5rem' }}
        />
      </Box>
    </Box>
  )
}

// ─── Split variant (bottom half of Home screen) ──────────────────────────────
// Renders in the bottom ~50% of the 600×1024 screen, alongside clock+bubbles
// in the top half. Smaller album art, compact metadata, full transport.

function NowPlayingSplit({ data, phoneLabel }: { data: NowPlayingData; phoneLabel?: string }) {
  const t = useHubTokens()
  const pct = data.durationMs > 0 ? (data.elapsedMs / data.durationMs) * 100 : 0
  const sourceLabel = [data.appName, phoneLabel].filter(Boolean).join(' · ')

  return (
    <Box
      data-testid="hub-now-playing-split"
      sx={{
        position: 'relative',
        width: '100%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        overflow: 'hidden',
        backgroundColor: '#0E1116',
        borderTop: `1px solid rgba(255,255,255,0.08)`,
        // Blurred album art background — atmosphere layer
        '&::before': data.artworkUrl
          ? {
              content: '""',
              position: 'absolute',
              inset: '-20%',
              backgroundImage: `url(${data.artworkUrl})`,
              backgroundSize: 'cover',
              backgroundPosition: 'center',
              filter: 'blur(60px) saturate(130%) brightness(0.4)',
              zIndex: 0
            }
          : undefined,
        // Dark vignette overlay
        '&::after': {
          content: '""',
          position: 'absolute',
          inset: 0,
          background: 'linear-gradient(to bottom, rgba(14,17,22,0.65) 0%, rgba(14,17,22,0.8) 100%)',
          zIndex: 1
        }
      }}
    >
      <Box
        sx={{
          position: 'relative',
          zIndex: 2,
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: 'clamp(0.75rem, 2.5vh, 1.25rem) clamp(1.5rem, 5vw, 2.5rem) clamp(0.75rem, 2vh, 1.25rem)',
          gap: 'clamp(0.5rem, 1.5vh, 0.75rem)'
        }}
      >
        {/* Album art — smaller for bottom-half split */}
        <Box
          sx={{
            width: 'clamp(120px, 35vw, 200px)',
            aspectRatio: '1 / 1',
            borderRadius: 'clamp(8px, 1.5vw, 14px)',
            overflow: 'hidden',
            flexShrink: 0,
            boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
            backgroundColor: 'rgba(255,255,255,0.06)',
            backgroundImage: data.artworkUrl ? `url(${data.artworkUrl})` : undefined,
            backgroundSize: 'cover',
            backgroundPosition: 'center',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            animation: 'hub-np-split-art-in 350ms ease-out',
            '@keyframes hub-np-split-art-in': {
              from: { opacity: 0, transform: 'scale(0.94)' },
              to: { opacity: 1, transform: 'scale(1)' }
            }
          }}
        >
          {!data.artworkUrl && (
            <MusicNoteIcon sx={{ fontSize: 'clamp(2rem, 8vw, 3rem)', color: 'rgba(255,255,255,0.25)' }} />
          )}
        </Box>

        {/* Metadata — compact */}
        <Box
          sx={{
            width: '100%',
            maxWidth: '440px',
            textAlign: 'center',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.1rem',
            flexShrink: 0
          }}
        >
          <Typography
            sx={{
              fontSize: 'clamp(1.1rem, 4vmin, 1.5rem)',
              fontWeight: 700,
              color: '#FFFFFF',
              lineHeight: 1.15,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              textShadow: '0 2px 8px rgba(0,0,0,0.4)'
            }}
          >
            {data.title || 'Unknown track'}
          </Typography>
          <Typography
            sx={{
              fontSize: 'clamp(0.85rem, 3vmin, 1.1rem)',
              fontWeight: 500,
              color: 'rgba(255,255,255,0.7)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap'
            }}
          >
            {data.artist || 'Unknown artist'}
          </Typography>
          {sourceLabel && (
            <Typography
              sx={{
                fontSize: 'clamp(0.7rem, 2.5vmin, 0.85rem)',
                fontWeight: 500,
                color: 'rgba(255,255,255,0.4)',
                marginTop: '0.15rem',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap'
              }}
            >
              {sourceLabel}
            </Typography>
          )}
        </Box>

        {/* Progress bar — compact */}
        <Box
          sx={{
            width: '100%',
            maxWidth: '440px',
            flexShrink: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: '0.2rem'
          }}
        >
          <Box
            sx={{
              width: '100%',
              height: '4px',
              borderRadius: '2px',
              backgroundColor: 'rgba(255,255,255,0.18)',
              overflow: 'hidden',
              position: 'relative'
            }}
          >
            <Box
              sx={{
                position: 'absolute',
                left: 0,
                top: 0,
                bottom: 0,
                width: `${pct}%`,
                backgroundColor: '#FFFFFF',
                borderRadius: '2px',
                transition: 'width 250ms linear'
              }}
            />
          </Box>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', width: '100%' }}>
            <Typography sx={{ fontSize: 'clamp(0.65rem, 2.2vmin, 0.8rem)', color: 'rgba(255,255,255,0.55)' }}>
              {formatTime(data.elapsedMs)}
            </Typography>
            <Typography sx={{ fontSize: 'clamp(0.65rem, 2.2vmin, 0.8rem)', color: 'rgba(255,255,255,0.55)' }}>
              {formatTime(data.durationMs)}
            </Typography>
          </Box>
        </Box>

        {/* Transport controls */}
        <TransportControls
          isPlaying={data.isPlaying}
          size="medium"
          sx={{ flexShrink: 0 }}
        />
      </Box>
    </Box>
  )
}

// ─── Compact variant (bar strip in launcher/phoneApp mode) ───────────────────

function NowPlayingCompact({ data, phoneLabel }: { data: NowPlayingData; phoneLabel?: string }) {
  const t = useHubTokens()

  return (
    <Box
      data-testid="hub-now-playing-compact"
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 'clamp(0.6rem, 2vw, 1rem)',
        width: '100%',
        marginTop: 'auto',
        paddingTop: 'clamp(0.4rem, 1vh, 0.75rem)'
      }}
    >
      {/* Album art thumbnail */}
      <Box
        sx={{
          width: 'clamp(2.5rem, 8vmin, 3rem)',
          height: 'clamp(2.5rem, 8vmin, 3rem)',
          borderRadius: 'clamp(4px, 1vmin, 8px)',
          overflow: 'hidden',
          flexShrink: 0,
          backgroundColor: t.surfaceMuted,
          backgroundImage: data.artworkUrl ? `url(${data.artworkUrl})` : undefined,
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: '0 2px 8px rgba(0,0,0,0.3)'
        }}
      >
        {!data.artworkUrl && (
          <MusicNoteIcon sx={{ fontSize: '1.2rem', color: t.textMuted }} />
        )}
      </Box>

      {/* Title + artist (truncated) */}
      <Box
        sx={{
          flex: 1,
          minWidth: 0,
          display: 'flex',
          flexDirection: 'column',
          gap: '0.1rem'
        }}
      >
        <Typography
          sx={{
            fontSize: 'clamp(0.85rem, 3vmin, 1.05rem)',
            fontWeight: 600,
            color: t.text,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            lineHeight: 1.2
          }}
        >
          {data.title || 'Unknown track'}
        </Typography>
        <Typography
          sx={{
            fontSize: 'clamp(0.72rem, 2.5vmin, 0.85rem)',
            fontWeight: 400,
            color: t.textMuted,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            lineHeight: 1.2
          }}
        >
          {data.artist || 'Unknown artist'}
        </Typography>
      </Box>

      {/* Transport controls */}
      <TransportControls isPlaying={data.isPlaying} size="small" />
    </Box>
  )
}

// ─── Shared transport controls ───────────────────────────────────────────────

interface TransportProps {
  isPlaying: boolean
  size: 'large' | 'medium' | 'small'
  sx?: Record<string, unknown>
}

function TransportControls({ isPlaying, size, sx }: TransportProps) {
  const send = useCallback((key: string) => (e: { stopPropagation?: () => void }) => {
    e?.stopPropagation?.()
    window.projection.ipc.sendCommand(key)
  }, [])

  const dims = size === 'large'
    ? { primary: 'clamp(3.5rem, 12vmin, 5rem)', secondary: 'clamp(2.75rem, 9vmin, 3.5rem)', icon: 'clamp(1.5rem, 5vmin, 2.1rem)', sIcon: 'clamp(1.25rem, 4vmin, 1.75rem)' }
    : size === 'medium'
    ? { primary: 'clamp(2.75rem, 9vmin, 3.5rem)', secondary: 'clamp(2.25rem, 7vmin, 2.75rem)', icon: 'clamp(1.25rem, 4vmin, 1.6rem)', sIcon: 'clamp(1.1rem, 3.5vmin, 1.4rem)' }
    : { primary: 'clamp(2rem, 6vmin, 2.5rem)', secondary: 'clamp(1.75rem, 5vmin, 2.1rem)', icon: 'clamp(1rem, 3vmin, 1.25rem)', sIcon: 'clamp(0.9rem, 2.8vmin, 1.1rem)' }

  const btn = (icon: ReactNode, key: string, isPrimary: boolean): ReactNode => (
    <Box
      role="button"
      aria-label={key}
      data-testid={`hub-np-${key}`}
      onClick={send(key)}
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: isPrimary ? dims.primary : dims.secondary,
        height: isPrimary ? dims.primary : dims.secondary,
        borderRadius: '50%',
        cursor: 'pointer',
        color: '#FFFFFF',
        backgroundColor: isPrimary && size !== 'small' ? 'rgba(255,255,255,0.12)' : 'transparent',
        backdropFilter: isPrimary && size !== 'small' ? 'blur(8px)' : undefined,
        transition: 'transform 100ms ease, background-color 160ms ease',
        '&:active': { transform: 'scale(0.92)' },
        '&:hover': size !== 'small' ? { backgroundColor: 'rgba(255,255,255,0.18)' } : { transform: 'scale(0.92)' }
      }}
    >
      {icon}
    </Box>
  )

  return (
    <Box
      data-testid="hub-np-transport"
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: size === 'large' ? 'clamp(0.75rem, 3vw, 1.5rem)' : 'clamp(0.25rem, 1vw, 0.5rem)',
        ...sx
      }}
    >
      {btn(<SkipPreviousIcon sx={{ fontSize: dims.sIcon }} />, 'prev', false)}
      {btn(
        isPlaying
          ? <PauseIcon sx={{ fontSize: dims.icon }} />
          : <PlayArrowIcon sx={{ fontSize: dims.icon }} />,
        'playPause',
        true
      )}
      {btn(<SkipNextIcon sx={{ fontSize: dims.sIcon }} />, 'next', false)}
    </Box>
  )
}
