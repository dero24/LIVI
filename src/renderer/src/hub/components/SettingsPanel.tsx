// [hub] §12.5: the settings panel — a full-width panel with section-based
// navigation, opened from the gear in the bar. It is the human surface for the
// intents hubd already owns (§7.5): forget a phone, reset calibration, restart
// LIVI, set audio devices, per-phone policies, and inspect network/service
// health. Every write goes through `window.hub.intent` so hubd remains the
// single mutation path (D7).
//
// Navigation: main view shows section cards. Tapping a section navigates to a
// detail view with a back button. Phone detail includes rename, forget,
// recalibration, policy toggles, and enrollment — all the per-phone controls
// that were previously crammed into a single scroll.
import { Box, Button, Divider, Drawer, IconButton, MenuItem, Select, Slider, Switch, Typography } from '@mui/material'
import SettingsIcon from '@mui/icons-material/Settings'
import CloseIcon from '@mui/icons-material/Close'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import ChevronRightIcon from '@mui/icons-material/ChevronRight'
import RestartAltIcon from '@mui/icons-material/RestartAlt'
import TuneIcon from '@mui/icons-material/Tune'
import WifiIcon from '@mui/icons-material/Wifi'
import PhoneIcon from '@mui/icons-material/PhoneIphone'
import VolumeUpIcon from '@mui/icons-material/VolumeUp'
import VolumeDownIcon from '@mui/icons-material/VolumeDown'
import VolumeOffIcon from '@mui/icons-material/VolumeOff'
import DisplaySettingsIcon from '@mui/icons-material/DisplaySettings'
import { type ReactNode, useCallback, useEffect, useState } from 'react'
import { useLiviStore } from '@store/store'
import type { HubPhone } from '../types'
import { useHubTokens } from '../useHubTokens'
import { isCalibrated, LANDING_TILES } from './Landing'
import { NamingSheet } from './NamingSheet'

export interface SettingsPanelProps {
  open: boolean
  onClose: () => void
  intent: (payload: Record<string, unknown>) => void
  projectingPhone: HubPhone | null
  phones: HubPhone[]
  onResetCalibration: () => void
  onRecalibrateApp?: (phoneId: string, appKey: string) => void
}

interface NetStatus {
  wlan0?: { operstate?: string; carrier?: boolean | null; rx_bytes?: number; tx_bytes?: number } | null
  gateway?: string | null
  'livi-kiosk'?: string
  hubd?: string
}

type View = 'main' | 'phone-detail' | 'audio' | 'display' | 'system'

// ─── shared bits ──────────────────────────────────────────────────────────────

function SectionTitle({ children }: { children: ReactNode }) {
  return (
    <Typography
      sx={{
        fontSize: '0.7rem',
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
        color: 'rgba(255,255,255,0.45)',
        margin: '0.75rem 0 0.25rem'
      }}
    >
      {children}
    </Typography>
  )
}

function NavRow({
  icon,
  title,
  subtitle,
  onClick,
  badge
}: {
  icon: ReactNode
  title: string
  subtitle: string
  onClick: () => void
  badge?: string
}) {
  const t = useHubTokens()
  return (
    <Box
      onClick={onClick}
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
        padding: '0.75rem 0.5rem',
        borderRadius: '8px',
        cursor: 'pointer',
        transition: 'background-color 0.15s',
        '&:hover': { backgroundColor: t.surfaceMuted },
        '&:active': { backgroundColor: t.surfaceMuted }
      }}
    >
      <Box sx={{ opacity: 0.85 }}>{icon}</Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography sx={{ fontSize: '0.95rem', fontWeight: 500 }}>{title}</Typography>
        <Typography sx={{ fontSize: '0.75rem', color: t.textMuted, lineHeight: 1.3 }}>
          {subtitle}
        </Typography>
      </Box>
      {badge && (
        <Box sx={{
          fontSize: '0.7rem', color: t.textMuted,
          backgroundColor: t.surfaceMuted, borderRadius: '10px', padding: '0.1rem 0.5rem'
        }}>
          {badge}
        </Box>
      )}
      <ChevronRightIcon sx={{ color: t.textMuted, fontSize: '1.2rem' }} />
    </Box>
  )
}

function ToggleRow({
  title,
  subtitle,
  checked,
  onChange
}: {
  title: string
  subtitle: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.5rem 0' }}>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography sx={{ fontSize: '0.9rem', fontWeight: 500 }}>{title}</Typography>
        <Typography sx={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.55)', lineHeight: 1.3 }}>
          {subtitle}
        </Typography>
      </Box>
      <Switch checked={checked} onChange={(_, v) => onChange(v)} size="small" />
    </Box>
  )
}

function PhoneAvatar({ phone, size = '2rem' }: { phone: HubPhone; size?: string }) {
  return (
    <Box sx={{
      width: size, height: size, borderRadius: '50%',
      backgroundColor: phone.person?.colour ?? '#4F7CAC',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      color: '#fff', fontSize: `calc(${size} * 0.4)`, fontWeight: 600,
      flexShrink: 0
    }}>
      {(phone.person?.name ?? phone.person?.deviceName ?? 'P').charAt(0).toUpperCase()}
    </Box>
  )
}

// ─── phone detail view ────────────────────────────────────────────────────────

function PhoneDetailView({
  phone,
  intent,
  onBack,
  onRecalibrateApp,
  onResetCalibration,
  isProjecting
}: {
  phone: HubPhone
  intent: (payload: Record<string, unknown>) => void
  onBack: () => void
  onRecalibrateApp?: (phoneId: string, appKey: string) => void
  onResetCalibration: () => void
  isProjecting: boolean
}) {
  const t = useHubTokens()
  const [renameOpen, setRenameOpen] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)

  const displayName = phone.person?.name || phone.person?.deviceName || 'Unknown'
  const deviceName = phone.person?.deviceName ?? '—'
  const subtitleParts = [phone.presence.level]
  if (phone.livi?.batteryLevel != null) subtitleParts.push(`${phone.livi.batteryLevel}%${phone.livi.batteryCharging ? ' charging' : ''}`)
  if (phone.platform) subtitleParts.push(phone.platform)
  if (phone.protocol) subtitleParts.push(phone.protocol)

  const policy = phone.policy ?? {}
  const run = async (key: string, fn: () => void) => {
    setBusy(key); setMsg(null)
    try { fn(); setMsg(`${key} sent`) } catch { setMsg(`${key} failed`) } finally { setBusy(null) }
  }

  const setPolicy = (key: string, value: unknown) => {
    intent({ type: 'phone.policy', phoneId: phone.phoneId, policy: { [key]: value } })
  }

  return (
    <Box>
      {/* header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
        <IconButton onClick={onBack} size="small" sx={{ color: t.text }}>
          <ArrowBackIcon fontSize="small" />
        </IconButton>
        <Typography sx={{ fontSize: '1rem', fontWeight: 500 }}>Phone</Typography>
      </Box>

      {msg && <Typography sx={{ fontSize: '0.8rem', color: '#58a6ff', marginBottom: '0.5rem' }}>{msg}</Typography>}

      {/* identity card */}
      <Box sx={{
        display: 'flex', alignItems: 'center', gap: '0.75rem',
        backgroundColor: t.surfaceMuted, borderRadius: '12px', padding: '0.75rem',
        marginBottom: '0.75rem'
      }}>
        <PhoneAvatar phone={phone} size="2.5rem" />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontSize: '1.05rem', fontWeight: 600 }}>{displayName}</Typography>
          <Typography sx={{ fontSize: '0.75rem', color: t.textMuted }}>
            {subtitleParts.join(' · ')}
          </Typography>
        </Box>
      </Box>

      {/* name section */}
      <SectionTitle>Identity</SectionTitle>
      <Box sx={{ padding: '0.25rem 0', marginBottom: '0.5rem' }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
          <Box>
            <Typography sx={{ fontSize: '0.8rem', color: t.textMuted }}>Name</Typography>
            <Typography sx={{ fontSize: '1rem', fontWeight: 600 }}>
              {phone.person?.name ?? '(not named)'}
            </Typography>
          </Box>
          <Box>
            <Typography sx={{ fontSize: '0.8rem', color: t.textMuted }}>Device</Typography>
            <Typography sx={{ fontSize: '1rem', fontWeight: 500 }}>{deviceName}</Typography>
          </Box>
        </Box>
        <Button
          fullWidth
          variant="outlined"
          onClick={() => setRenameOpen(true)}
          sx={{
            color: t.text, borderColor: t.border, textTransform: 'none',
            fontSize: '0.9rem', padding: '0.5rem', marginTop: '0.25rem'
          }}
        >
          {phone.person?.name ? 'Rename phone' : 'Name this phone'}
        </Button>
      </Box>

      {/* behavior */}
      <SectionTitle>Behavior</SectionTitle>
      <ToggleRow
        title="Show notifications"
        subtitle="Forward phone notifications to the hub"
        checked={policy.showNotifications !== false}
        onChange={(v) => setPolicy('showNotifications', v)}
      />

      {/* calibration */}
      <SectionTitle>Calibration</SectionTitle>
      {phone.presence.rank < 2 ? (
        <Typography sx={{ fontSize: '0.8rem', color: t.textMuted, padding: '0.25rem 0' }}>
          Dock and project this phone to calibrate app positions.
        </Typography>
      ) : (
        <Box>
          {LANDING_TILES.filter((tile) => tile.calibratable).map((tile) => {
            const calibrated = isCalibrated(phone.phoneId, tile.key)
            return (
              <Box key={tile.key} sx={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.25rem 0' }}>
                <Box sx={{ fontSize: '1.1rem' }}>{tile.icon}</Box>
                <Box sx={{ flex: 1 }}>
                  <Typography sx={{ fontSize: '0.85rem' }}>{tile.label}</Typography>
                  <Typography sx={{ fontSize: '0.7rem', color: calibrated ? t.ok : t.textMuted }}>
                    {calibrated ? 'Calibrated' : 'Not calibrated'}
                  </Typography>
                </Box>
                <Button
                  size="small"
                  variant="outlined"
                  disabled={!isProjecting}
                  onClick={() => onRecalibrateApp?.(phone.phoneId, tile.key)}
                  sx={{ textTransform: 'none', fontSize: '0.75rem' }}
                >
                  Recalibrate
                </Button>
              </Box>
            )
          })}
          {isProjecting && (
            <Button
              size="small"
              variant="text"
              onClick={onResetCalibration}
              sx={{ color: t.danger, textTransform: 'none', fontSize: '0.75rem', marginTop: '0.25rem' }}
            >
              Reset all calibration
            </Button>
          )}
        </Box>
      )}

      {/* companion / enrollment */}
      <SectionTitle>Reachability</SectionTitle>
      <Box sx={{ padding: '0.25rem 0' }}>
        <Typography sx={{ fontSize: '0.8rem', color: t.textMuted, marginBottom: '0.25rem' }}>
          {phone.companion
            ? 'Companion app enrolled — reachable when not docked.'
            : 'No companion app. This phone is only reachable when docked.'}
        </Typography>
        {!phone.companion && (
          <Button
            size="small"
            variant="outlined"
            onClick={() => intent({ type: 'phone.enrolStart', phoneId: phone.phoneId })}
            sx={{ color: t.ring, borderColor: t.border, textTransform: 'none', fontSize: '0.8rem' }}
          >
            Enroll companion app
          </Button>
        )}
      </Box>

      {/* danger zone */}
      <SectionTitle>Danger zone</SectionTitle>
      <Button
        size="small"
        color="error"
        variant="outlined"
        disabled={busy === 'Forget'}
        onClick={() => {
          if (confirm(`Forget ${displayName}? This removes the phone from the hub.`)) {
            run('Forget', () => intent({ type: 'phone.forget', phoneId: phone.phoneId }))
          }
        }}
        sx={{ textTransform: 'none', fontSize: '0.8rem', marginTop: '0.25rem' }}
      >
        Forget this phone
      </Button>

      {renameOpen && (
        <NamingSheet
          phone={phone}
          open
          onClose={() => setRenameOpen(false)}
          onRename={(phoneId, name) => {
            intent({ type: 'phone.rename', phoneId, name })
            setRenameOpen(false)
          }}
        />
      )}
    </Box>
  )
}

// ─── audio view ───────────────────────────────────────────────────────────────

function AudioView({
  onBack,
  intent,
  audioDevices,
  onRefresh,
  audioOutput,
  audioInput,
  huVolume,
  busy,
  msg
}: {
  onBack: () => void
  intent: (payload: Record<string, unknown>) => void
  audioDevices: { sinks: { id: string; name: string }[]; sources: { id: string; name: string }[] } | null
  onRefresh: () => void
  audioOutput: string
  audioInput: string
  huVolume: number
  busy: string | null
  msg: string | null
}) {
  const t = useHubTokens()
  // [hub] work-log 38: local volume state for responsive slider dragging.
  // Syncs from config when not actively dragging.
  const [volDraft, setVolDraft] = useState<number>(Math.round(huVolume * 100))
  useEffect(() => { setVolDraft(Math.round(huVolume * 100)) }, [huVolume])
  const VolumeIcon = volDraft === 0 ? VolumeOffIcon : volDraft < 33 ? VolumeDownIcon : VolumeUpIcon
  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
        <IconButton onClick={onBack} size="small" sx={{ color: t.text }}>
          <ArrowBackIcon fontSize="small" />
        </IconButton>
        <Typography sx={{ fontSize: '1rem', fontWeight: 500 }}>Audio</Typography>
      </Box>

      {msg && <Typography sx={{ fontSize: '0.8rem', color: '#58a6ff', marginBottom: '0.5rem' }}>{msg}</Typography>}

      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.25rem' }}>
        <Typography sx={{ fontSize: '0.7rem', color: t.textMuted }}>
          {audioDevices ? `${audioDevices.sinks.length} outputs · ${audioDevices.sources.length} inputs` : 'Loading…'}
        </Typography>
        <Button
          size="small"
          variant="text"
          disabled={busy === 'RefreshAudio'}
          onClick={onRefresh}
          sx={{ color: t.textMuted, textTransform: 'none', fontSize: '0.75rem', minWidth: 'auto' }}
        >
          ↻ Refresh
        </Button>
      </Box>

      {/* [hub] work-log 38: system volume slider — controls pactl sink volume
          via the huVolume config key + huVolumeLinkSystem. */}
      <Box sx={{ padding: '0.5rem 0 0.75rem' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.35rem' }}>
          <VolumeIcon sx={{ color: t.text, fontSize: '1.1rem' }} />
          <Typography sx={{ fontSize: '0.85rem', fontWeight: 500 }}>Volume</Typography>
          <Typography sx={{ fontSize: '0.75rem', color: t.textMuted, marginLeft: 'auto' }}>{volDraft}%</Typography>
        </Box>
        <Slider
          value={volDraft}
          min={0}
          max={100}
          step={1}
          onChange={(_, v) => setVolDraft(v as number)}
          onChangeCommitted={(_, v) => {
            intent({ type: 'settings.set', settings: { huVolume: (v as number) / 100 } })
          }}
          sx={{
            color: t.text,
            '& .MuiSlider-thumb': { width: 18, height: 18 },
            '& .MuiSlider-rail': { opacity: 0.3 },
            '& .MuiSlider-track': { border: 'none' }
          }}
        />
      </Box>

      <Box sx={{ padding: '0.5rem 0' }}>
        <Typography sx={{ fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.25rem' }}>Output device</Typography>
        <Select
          size="small"
          fullWidth
          value={audioOutput}
          displayEmpty
          onChange={(e) => {
            intent({ type: 'settings.set', settings: { audioOutputDevice: e.target.value } })
          }}
          sx={{
            color: t.text,
            '& .MuiSelect-icon': { color: t.text },
            '& .MuiOutlinedInput-notchedOutline': { borderColor: t.border }
          }}
        >
          <MenuItem value=""><em>System default</em></MenuItem>
          {audioDevices?.sinks.map((s) => (
            <MenuItem key={s.id} value={s.id} sx={{ fontSize: '0.75rem' }}>{s.name}</MenuItem>
          ))}
        </Select>
        <Typography sx={{ fontSize: '0.7rem', color: t.textMuted, marginTop: '0.15rem' }}>
          Ringtone and call audio play through this device.
        </Typography>
      </Box>

      <Box sx={{ padding: '0.5rem 0' }}>
        <Typography sx={{ fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.25rem' }}>Input device</Typography>
        <Select
          size="small"
          fullWidth
          value={audioInput}
          displayEmpty
          onChange={(e) => {
            intent({ type: 'settings.set', settings: { audioInputDevice: e.target.value } })
          }}
          sx={{
            color: t.text,
            '& .MuiSelect-icon': { color: t.text },
            '& .MuiOutlinedInput-notchedOutline': { borderColor: t.border }
          }}
        >
          <MenuItem value=""><em>System default</em></MenuItem>
          {audioDevices?.sources.map((s) => (
            <MenuItem key={s.id} value={s.id} sx={{ fontSize: '0.75rem' }}>{s.name}</MenuItem>
          ))}
        </Select>
        <Typography sx={{ fontSize: '0.7rem', color: t.textMuted, marginTop: '0.15rem' }}>
          Microphone for hub-side call audio.
        </Typography>
      </Box>
    </Box>
  )
}

// ─── system view ──────────────────────────────────────────────────────────────

function SystemView({
  onBack,
  intent,
  net,
  netErr,
  busy,
  run
}: {
  onBack: () => void
  intent: (payload: Record<string, unknown>) => void
  net: NetStatus | null
  netErr: string | null
  busy: string | null
  run: (key: string, fn: () => void) => void
}) {
  const t = useHubTokens()
  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
        <IconButton onClick={onBack} size="small" sx={{ color: t.text }}>
          <ArrowBackIcon fontSize="small" />
        </IconButton>
        <Typography sx={{ fontSize: '1rem', fontWeight: 500 }}>System</Typography>
      </Box>

      <SectionTitle>Services</SectionTitle>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.5rem 0' }}>
        <RestartAltIcon sx={{ opacity: 0.85 }} />
        <Box sx={{ flex: 1 }}>
          <Typography sx={{ fontSize: '0.9rem', fontWeight: 500 }}>Restart LIVI</Typography>
          <Typography sx={{ fontSize: '0.75rem', color: t.textMuted }}>
            Restarts the kiosk. AA sessions drop and re-establish.
          </Typography>
        </Box>
        <Button
          size="small"
          variant="outlined"
          disabled={busy === 'Restart'}
          onClick={() => run('Restart', () => intent({ type: 'system.restartLivi' }))}
          sx={{ textTransform: 'none', fontSize: '0.75rem' }}
        >
          Restart
        </Button>
      </Box>

      <SectionTitle>Network</SectionTitle>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.5rem 0' }}>
        <WifiIcon sx={{ opacity: 0.85 }} />
        <Box sx={{ flex: 1 }}>
          <Typography sx={{ fontSize: '0.9rem', fontWeight: 500 }}>Reset WiFi</Typography>
          <Typography sx={{ fontSize: '0.75rem', color: t.textMuted }}>
            Reconnects wlan0 if the hub lost its network.
          </Typography>
        </Box>
        <Button
          size="small"
          variant="outlined"
          disabled={busy === 'Wifi'}
          onClick={() => run('Wifi', () => fetch('http://127.0.0.1:8125/reset-wifi').catch(() => {}))}
          sx={{ textTransform: 'none', fontSize: '0.75rem' }}
        >
          Reset
        </Button>
      </Box>

      {netErr && (
        <Typography sx={{ fontSize: '0.75rem', color: t.danger, padding: '0.25rem 0' }}>
          Status unavailable: {netErr}
        </Typography>
      )}
      {net && (
        <Box sx={{
          fontSize: '0.8rem', color: t.text, lineHeight: 1.6,
          backgroundColor: t.surfaceMuted, borderRadius: '8px', padding: '0.5rem 0.75rem',
          marginTop: '0.25rem'
        }}>
          <Box>wlan0: <b>{net.wlan0?.operstate ?? '?'}</b>{net.wlan0?.carrier === false ? ' (no carrier)' : ''}</Box>
          <Box>gateway: <b>{net.gateway ?? '—'}</b></Box>
          <Box>livi-kiosk: <b>{net['livi-kiosk'] ?? '?'}</b></Box>
          <Box>hubd: <b>{net.hubd ?? '?'}</b></Box>
        </Box>
      )}
      {!net && !netErr && (
        <Typography sx={{ fontSize: '0.75rem', color: t.textMuted }}>Loading…</Typography>
      )}
      <Typography sx={{ fontSize: '0.7rem', color: t.textMuted, marginTop: '0.5rem' }}>
        Recovery console: http://10.0.0.123:8125/
      </Typography>
    </Box>
  )
}

// ─── main settings panel ──────────────────────────────────────────────────────

export function SettingsPanel({
  open,
  onClose,
  intent,
  projectingPhone,
  phones,
  onResetCalibration,
  onRecalibrateApp
}: SettingsPanelProps) {
  const t = useHubTokens()
  const [view, setView] = useState<View>('main')
  const [selectedPhoneId, setSelectedPhoneId] = useState<string | null>(null)
  const [net, setNet] = useState<NetStatus | null>(null)
  const [netErr, setNetErr] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const liviSettings = useLiviStore((s) => s.settings)
  const [audioDevices, setAudioDevices] = useState<{ sinks: { id: string; name: string }[]; sources: { id: string; name: string }[] } | null>(null)
  const audioOutput = liviSettings?.audioOutputDevice ?? ''
  const audioInput = liviSettings?.audioInputDevice ?? ''

  // Reset to main view when panel closes
  useEffect(() => {
    if (!open) {
      setView('main')
      setSelectedPhoneId(null)
      setMsg(null)
    }
  }, [open])

  // Fetch network status
  useEffect(() => {
    if (!open) return
    let cancelled = false
    setNet(null)
    setNetErr(null)
    fetch('http://127.0.0.1:8125/status', { cache: 'no-store' })
      .then((r) => r.json())
      .then((s: NetStatus) => !cancelled && setNet(s))
      .catch((e) => !cancelled && setNetErr(String(e)))
    return () => { cancelled = true }
  }, [open])

  // Fetch audio devices + auto-refresh on USB events
  const fetchAudioDevices = useCallback(() => {
    fetch('http://127.0.0.1:8123/audio-devices', { cache: 'no-store' })
      .then((r) => r.json())
      .then((d: { sinks: { id: string; name: string }[]; sources: { id: string; name: string }[] }) => setAudioDevices(d))
      .catch(() => {})
  }, [])
  useEffect(() => {
    if (!open) return
    fetchAudioDevices()
    const usbHandler = (_evt: unknown, ...args: unknown[]) => {
      const data = (args[0] ?? {}) as { type?: string }
      if (data.type && ['attach', 'plugged', 'detach', 'unplugged'].includes(data.type)) {
        setTimeout(fetchAudioDevices, 500)
      }
    }
    const unsubscribe = window.projection?.usb?.listenForEvents?.(usbHandler)
    return () => { unsubscribe?.() }
  }, [open, fetchAudioDevices])

  const run = async (key: string, fn: () => void) => {
    setBusy(key); setMsg(null)
    try { fn(); setMsg(`${key} sent`) } catch { setMsg(`${key} failed`) } finally { setBusy(null) }
  }

  const refreshAudio = () => {
    setBusy('RefreshAudio')
    fetch('http://127.0.0.1:8123/audio-devices', { cache: 'no-store' })
      .then((r) => r.json())
      .then((d: { sinks: { id: string; name: string }[]; sources: { id: string; name: string }[] }) => {
        setAudioDevices(d)
        setMsg(`Found ${d.sinks.length} outputs, ${d.sources.length} inputs`)
      })
      .catch(() => setMsg('Failed to refresh audio devices'))
      .finally(() => setBusy(null))
  }

  const selectedPhone = phones.find((p) => p.phoneId === selectedPhoneId) ?? null

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      slotProps={{
        paper: {
          sx: {
            width: 'min(520px, 100vw)',
            backgroundColor: t.surface,
            color: t.text,
            padding: '1rem 1.25rem 2rem',
            overflowY: 'auto'
          }
        }
      }}
    >
      {/* header — changes per view */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {view === 'main' ? (
            <>
              <SettingsIcon />
              <Typography sx={{ fontSize: '1.1rem', fontWeight: 500 }}>Settings</Typography>
            </>
          ) : (
            <Typography sx={{ fontSize: '1.1rem', fontWeight: 500 }}>
              {view === 'phone-detail' ? 'Phone' : view === 'audio' ? 'Audio' : view === 'display' ? 'Display' : 'System'}
            </Typography>
          )}
        </Box>
        <IconButton onClick={onClose} size="small" sx={{ color: t.text }}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </Box>
      <Divider sx={{ borderColor: t.border, marginBottom: '0.5rem' }} />

      {msg && view !== 'phone-detail' && view !== 'audio' && (
        <Typography sx={{ fontSize: '0.8rem', color: '#58a6ff', marginBottom: '0.5rem' }}>{msg}</Typography>
      )}

      {/* ─── main view: section cards ─── */}
      {view === 'main' && (
        <Box>
          {/* phones section */}
          <SectionTitle>Phones</SectionTitle>
          {phones.length === 0 ? (
            <Typography sx={{ fontSize: '0.8rem', color: t.textMuted, padding: '0.5rem 0' }}>
              No phones known. Dock a phone to begin.
            </Typography>
          ) : (
            phones.map((p) => {
              const displayName = p.person?.name || p.person?.deviceName || 'Unknown'
              const subtitleParts = [p.presence.level]
              if (p.livi?.batteryLevel != null) subtitleParts.push(`${p.livi.batteryLevel}%`)
              if (p.platform) subtitleParts.push(p.platform)
              return (
                <NavRow
                  key={p.phoneId}
                  icon={<PhoneAvatar phone={p} />}
                  title={displayName}
                  subtitle={subtitleParts.join(' · ')}
                  badge={p.presence.level === 'projecting' ? 'active' : undefined}
                  onClick={() => { setSelectedPhoneId(p.phoneId); setView('phone-detail') }}
                />
              )
            })
          )}

          {/* audio section */}
          <SectionTitle>Device</SectionTitle>
          <NavRow
            icon={<VolumeUpIcon />}
            title="Audio"
            subtitle="Output, input, and ringtone devices"
            onClick={() => setView('audio')}
          />
          <NavRow
            icon={<DisplaySettingsIcon />}
            title="Display"
            subtitle="Brightness, night mode, appearance"
            onClick={() => setView('display')}
          />

          {/* system section */}
          <SectionTitle>Hub</SectionTitle>
          <NavRow
            icon={<TuneIcon />}
            title="System"
            subtitle="Restart, network, diagnostics"
            onClick={() => setView('system')}
          />
        </Box>
      )}

      {/* ─── phone detail view ─── */}
      {view === 'phone-detail' && selectedPhone && (
        <PhoneDetailView
          phone={selectedPhone}
          intent={intent}
          onBack={() => setView('main')}
          onRecalibrateApp={onRecalibrateApp}
          onResetCalibration={onResetCalibration}
          isProjecting={selectedPhone.presence.level === 'projecting'}
        />
      )}
      {view === 'phone-detail' && !selectedPhone && (
        <Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
            <IconButton onClick={() => setView('main')} size="small" sx={{ color: t.text }}>
              <ArrowBackIcon fontSize="small" />
            </IconButton>
          </Box>
          <Typography sx={{ fontSize: '0.8rem', color: t.textMuted }}>Phone no longer available.</Typography>
        </Box>
      )}

      {/* ─── audio view ─── */}
      {view === 'audio' && (
        <AudioView
          onBack={() => setView('main')}
          intent={intent}
          audioDevices={audioDevices}
          onRefresh={refreshAudio}
          audioOutput={audioOutput}
          audioInput={audioInput}
          huVolume={liviSettings?.huVolume ?? 0.95}
          busy={busy}
          msg={msg}
        />
      )}

      {/* ─── display view (placeholder for future night mode / brightness) ─── */}
      {view === 'display' && (
        <Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
            <IconButton onClick={() => setView('main')} size="small" sx={{ color: t.text }}>
              <ArrowBackIcon fontSize="small" />
            </IconButton>
            <Typography sx={{ fontSize: '1rem', fontWeight: 500 }}>Display</Typography>
          </Box>
          <Typography sx={{ fontSize: '0.8rem', color: t.textMuted, padding: '0.5rem 0' }}>
            Night mode, brightness, and appearance settings will be available here.
          </Typography>
        </Box>
      )}

      {/* ─── system view ─── */}
      {view === 'system' && (
        <SystemView
          onBack={() => setView('main')}
          intent={intent}
          net={net}
          netErr={netErr}
          busy={busy}
          run={run}
        />
      )}
    </Drawer>
  )
}
