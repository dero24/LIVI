import AndroidIcon from '@mui/icons-material/Android'
import BoltIcon from '@mui/icons-material/Bolt'
import CableOutlinedIcon from '@mui/icons-material/CableOutlined'
import CallEndIcon from '@mui/icons-material/CallEnd'
import CallIcon from '@mui/icons-material/Call'
import DeviceHubIcon from '@mui/icons-material/DeviceHub'
import DirectionsCarIcon from '@mui/icons-material/DirectionsCar'
import HomeRoundedIcon from '@mui/icons-material/HomeRounded'
import MicIcon from '@mui/icons-material/Mic'
import PauseIcon from '@mui/icons-material/Pause'
import PhoneIphoneIcon from '@mui/icons-material/PhoneIphone'
import PlayArrowIcon from '@mui/icons-material/PlayArrow'
import SkipNextIcon from '@mui/icons-material/SkipNext'
import SkipPreviousIcon from '@mui/icons-material/SkipPrevious'
import WifiOutlinedIcon from '@mui/icons-material/WifiOutlined'
import { Box, Typography, useTheme } from '@mui/material'
import { alpha } from '@mui/material/styles'
import { type ReactNode, useMemo, useState } from 'react'
import { useMediaState } from '@renderer/components/pages/media/hooks/useMediaState'
import { type DeviceView, selectDevice, useDevices } from '@renderer/components/pages/settings/pages/devices/useDevices'
import { useStatusStore } from '@renderer/store/store'

const protocolIcon = (protocol?: DeviceView['protocol'], size = 40) => {
  const sx = { fontSize: size }
  if (protocol === 'androidauto') return <AndroidIcon sx={sx} />
  if (protocol === 'carplay') return <PhoneIphoneIcon sx={sx} />
  return <DirectionsCarIcon sx={sx} />
}

const protocolLabel = (protocol?: DeviceView['protocol']) =>
  protocol === 'androidauto' ? 'Android Auto' : protocol === 'carplay' ? 'CarPlay' : 'Device'

const sourceIcon = (d: DeviceView, size = 18) => {
  const sx = { fontSize: size }
  if (d.source === 'dongle') return <DeviceHubIcon sx={sx} />
  if (d.lastTransport === 'usb') return <CableOutlinedIcon sx={sx} />
  if (d.lastTransport === 'wifi') return <WifiOutlinedIcon sx={sx} />
  return null
}

const batteryColor = (pct: number) => (pct < 10 ? '#ff3b30' : pct < 20 ? '#ffcc00' : '#34c759')

const BatteryIcon = ({ level, charging }: { level: number; charging?: boolean }) => {
  const pct = Math.max(0, Math.min(100, Math.round(level)))
  const fillW = Math.max(3, (42 * pct) / 100)
  return (
    <span title={`${pct}%${charging ? ' charging' : ''}`} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
      <svg width={32} height={14} viewBox="0 0 32 14">
        <rect x={1} y={1} width={27} height={12} rx={2} fill="none" stroke="currentColor" strokeWidth={1} />
        <rect x={28} y={4} width={3} height={6} rx={1} fill="currentColor" />
        <rect x={3} y={3} width={fillW} height={8} rx={1} fill={batteryColor(pct)} opacity={0.9} />
      </svg>
      <span style={{ fontSize: 10, fontWeight: 700 }}>{pct}</span>
      {charging ? <BoltIcon sx={{ fontSize: 12, color: '#34c759' }} /> : null}
    </span>
  )
}

const SignalBars = ({ level }: { level: number }) => {
  const n = Math.max(0, Math.min(5, Math.round(level)))
  return (
    <span style={{ display: 'inline-flex', alignItems: 'flex-end', gap: 1, height: 12 }}>
      {[4, 6, 8, 10, 12].map((h, i) => (
        <span
          key={h}
          style={{
            width: 2,
            height: h,
            borderRadius: 1,
            background: i < n ? 'currentColor' : 'rgba(128,128,128,0.4)'
          }}
        />
      ))}
    </span>
  )
}

const sendCmd = (cmd: string) => {
  try {
    window.projection?.ipc?.sendCommand?.(cmd)
  } catch {}
}

const ActionButton = ({
  label,
  icon,
  onClick,
  onPointerDown,
  onPointerUp,
  large = false
}: {
  label: string
  icon: ReactNode
  onClick?: () => void
  onPointerDown?: () => void
  onPointerUp?: () => void
  large?: boolean
}) => {
  const theme = useTheme()
  const size = large ? 72 : 52
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      onPointerDown={onPointerDown}
      onPointerUp={onPointerUp}
      onPointerLeave={onPointerUp}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 4,
        width: size,
        height: size,
        borderRadius: 16,
        border: `2px solid ${theme.palette.divider}`,
        background: alpha(theme.palette.background.paper, 0.9),
        color: theme.palette.text.primary,
        cursor: 'pointer',
        pointerEvents: 'auto'
      }}
    >
      {icon}
      <span style={{ fontSize: 9, fontWeight: 600 }}>{label}</span>
    </button>
  )
}

export const Home = () => {
  const theme = useTheme()
  const devices = useDevices()
  const { snap } = useMediaState(true)
  const isStreaming = useStatusStore((s) => s.isStreaming)
  const [simpleMode, setSimpleMode] = useState(false)

  const activeDevice = useMemo(() => devices.find((d) => d.status === 'active'), [devices])
  const isPlaying = snap?.payload.media?.MediaPlayStatus === 1

  const onSelect = async (d: DeviceView) => {
    if (d.status === 'offline') return
    await selectDevice(d.id)
  }

  return (
    <Box
      sx={{
        position: 'absolute',
        inset: 0,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        pointerEvents: 'none',
        p: 2,
        boxSizing: 'border-box',
        gap: 2
      }}
    >
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          p: 1.5,
          borderRadius: 3,
          bgcolor: alpha(theme.palette.background.paper, 0.85),
          pointerEvents: 'auto'
        }}
      >
        <Typography variant="h6" sx={{ fontWeight: 700 }}>
          Home Hub
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {activeDevice ? (
            <Typography variant="body2" color="text.secondary">
              {activeDevice.name || activeDevice.model || activeDevice.id}
            </Typography>
          ) : (
            <Typography variant="body2" color="text.secondary">
              {isStreaming ? 'Streaming' : 'No phone'}
            </Typography>
          )}
          <button
            type="button"
            onClick={() => setSimpleMode((p) => !p)}
            style={{
              padding: '6px 12px',
              borderRadius: 12,
              border: `1px solid ${theme.palette.divider}`,
              background: 'transparent',
              color: theme.palette.text.secondary,
              fontSize: 12,
              cursor: 'pointer'
            }}
          >
            {simpleMode ? 'Std' : 'Simple'}
          </button>
        </Box>
      </Box>

      <Box
        sx={{
          display: 'flex',
          flexDirection: 'column',
          gap: 2,
          pointerEvents: 'auto'
        }}
      >
        <Box
          sx={{
            display: 'flex',
            justifyContent: 'space-around',
            alignItems: 'center',
            p: 1.5,
            borderRadius: 3,
            bgcolor: alpha(theme.palette.background.paper, 0.85)
          }}
        >
          <ActionButton
            label="Home"
            icon={<HomeRoundedIcon sx={{ fontSize: simpleMode ? 40 : 28 }} />}
            onClick={() => sendCmd('home')}
            large={simpleMode}
          />
          <ActionButton
            label={isPlaying ? 'Pause' : 'Play'}
            icon={
              isPlaying ? (
                <PauseIcon sx={{ fontSize: simpleMode ? 40 : 28 }} />
              ) : (
                <PlayArrowIcon sx={{ fontSize: simpleMode ? 40 : 28 }} />
              )
            }
            onClick={() => sendCmd(isPlaying ? 'pause' : 'play')}
            large={simpleMode}
          />
          <ActionButton
            label="Next"
            icon={<SkipNextIcon sx={{ fontSize: simpleMode ? 40 : 28 }} />}
            onClick={() => sendCmd('next')}
            large={simpleMode}
          />
          <ActionButton
            label="Prev"
            icon={<SkipPreviousIcon sx={{ fontSize: simpleMode ? 40 : 28 }} />}
            onClick={() => sendCmd('prev')}
            large={simpleMode}
          />
          <ActionButton
            label="Answer"
            icon={<CallIcon sx={{ fontSize: simpleMode ? 40 : 28 }} />}
            onClick={() => sendCmd('acceptPhone')}
            large={simpleMode}
          />
          <ActionButton
            label="Hang up"
            icon={<CallEndIcon sx={{ fontSize: simpleMode ? 40 : 28 }} />}
            onClick={() => sendCmd('rejectPhone')}
            large={simpleMode}
          />
          <ActionButton
            label="Voice"
            icon={<MicIcon sx={{ fontSize: simpleMode ? 40 : 28 }} />}
            onPointerDown={() => sendCmd('voiceAssistant')}
            onPointerUp={() => sendCmd('voiceAssistantRelease')}
            large={simpleMode}
          />
        </Box>

        <Box
          sx={{
            display: 'flex',
            flexDirection: 'row',
            gap: 2,
            p: 1.5,
            borderRadius: 3,
            bgcolor: alpha(theme.palette.background.paper, 0.85)
          }}
        >
          {devices.length === 0 ? (
            <Box sx={{ flex: 1, textAlign: 'center', py: 4 }}>
              <Typography variant="body1" color="text.secondary">
                No phone connected
              </Typography>
            </Box>
          ) : (
            devices.map((d) => {
              const active = d.status === 'active'
              const offline = d.status === 'offline'
              const accent = active
                ? theme.palette.secondary.main
                : offline
                  ? theme.palette.text.disabled
                  : theme.palette.text.primary

              return (
                <button
                  key={d.id}
                  type="button"
                  disabled={offline}
                  onClick={() => onSelect(d)}
                  style={{
                    flex: 1,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 8,
                    padding: 16,
                    borderRadius: 20,
                    border: `3px solid ${accent}`,
                    background: theme.palette.background.paper,
                    color: theme.palette.text.primary,
                    opacity: offline ? 0.5 : 1,
                    cursor: offline ? 'default' : 'pointer',
                    textAlign: 'center',
                    minHeight: 140,
                    pointerEvents: 'auto'
                  }}
                >
                  <Box sx={{ color: accent }}>{protocolIcon(d.protocol, simpleMode ? 64 : 48)}</Box>
                  <Box>
                    <Typography variant={simpleMode ? 'h5' : 'h6'} sx={{ fontWeight: 700 }}>
                      {d.name || d.model || d.id}
                    </Typography>
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 0.5, mt: 0.5 }}
                    >
                      {protocolLabel(d.protocol)}
                      {sourceIcon(d)}
                    </Typography>
                  </Box>
                  <Box
                    sx={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 2,
                      fontSize: 12,
                      color: 'text.secondary'
                    }}
                  >
                    {typeof d.batteryLevel === 'number' ? (
                      <BatteryIcon level={d.batteryLevel} charging={d.batteryCharging} />
                    ) : null}
                    {typeof d.signalStrength === 'number' ? <SignalBars level={d.signalStrength} /> : null}
                    <Typography variant="caption" sx={{ color: accent, fontWeight: 600 }}>
                      {active ? 'Active' : offline ? 'Offline' : 'Available'}
                    </Typography>
                  </Box>
                </button>
              )
            })
          )}
        </Box>
      </Box>
    </Box>
  )
}
