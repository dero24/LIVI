// [hub] §12.5: the settings panel — a right-anchored drawer opened from the
// gear in the bar. It is the human surface for the intents hubd already owns
// (§7.5): forget a phone, reset calibration, restart LIVI, change display
// dimensions, and inspect network/service health. Per the plan it is a node in
// LIVI's own settings surface — here a lightweight MUI Drawer rather than the
// full schema tree, since the hub only owns a handful of keys (SETTINGS_ALLOWLIST
// in hubd/hubd/intents.py). Every write goes through `window.hub.intent` so
// hubd remains the single mutation path (D7).
import { Box, Button, Divider, Drawer, IconButton, Typography } from '@mui/material'
import SettingsIcon from '@mui/icons-material/Settings'
import CloseIcon from '@mui/icons-material/Close'
import RestartAltIcon from '@mui/icons-material/RestartAlt'
import DeleteIcon from '@mui/icons-material/Delete'
import TuneIcon from '@mui/icons-material/Tune'
import { type CSSProperties, type ReactNode, useEffect, useState } from 'react'
import { useLiviStore } from '@store/store'
import type { HubPhone } from '../types'
import { useHubTokens } from '../useHubTokens'

export interface SettingsPanelProps {
  open: boolean
  onClose: () => void
  intent: (payload: Record<string, unknown>) => void
  projectingPhone: HubPhone | null
  phones: HubPhone[]
  onResetCalibration: () => void
}

interface NetStatus {
  wlan0?: { operstate?: string; carrier?: boolean | null; rx_bytes?: number; tx_bytes?: number } | null
  gateway?: string | null
  'livi-kiosk'?: string
  hubd?: string
  'wlan0-watchdog'?: string
}

function Row({
  icon,
  title,
  subtitle,
  action,
  danger
}: {
  icon: ReactNode
  title: string
  subtitle: string
  action: ReactNode
  danger?: boolean
}) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.5rem 0' }}>
      <Box sx={{ opacity: 0.85 }}>{icon}</Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography sx={{ fontSize: '0.95rem', fontWeight: 500, color: danger ? '#ff6b6b' : 'inherit' }}>
          {title}
        </Typography>
        <Typography sx={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.55)', lineHeight: 1.3 }}>
          {subtitle}
        </Typography>
      </Box>
      {action}
    </Box>
  )
}

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

export function SettingsPanel({
  open,
  onClose,
  intent,
  projectingPhone,
  phones,
  onResetCalibration
}: SettingsPanelProps) {
  const t = useHubTokens()
  const settings = useLiviStore((s) => s.settings)
  const [net, setNet] = useState<NetStatus | null>(null)
  const [netErr, setNetErr] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)

  // Display settings local edit state (initialized from the live config).
  const [pw, setPw] = useState('')
  const [ph, setPh] = useState('')
  const [pdpi, setPdpi] = useState('')

  useEffect(() => {
    if (settings) {
      setPw(String(settings.projectionWidth ?? ''))
      setPh(String(settings.projectionHeight ?? ''))
      setPdpi(String(settings.projectionDpi ?? ''))
    }
  }, [settings, open])

  // Fetch network/service status from the hearth-recovery server (read-only
  // /status needs no token). It runs on the Pi at localhost:8125.
  useEffect(() => {
    if (!open) return
    let cancelled = false
    setNet(null)
    setNetErr(null)
    fetch('http://localhost:8125/status', { cache: 'no-store' })
      .then((r) => r.json())
      .then((s: NetStatus) => !cancelled && setNet(s))
      .catch((e) => !cancelled && setNetErr(String(e)))
    return () => {
      cancelled = true
    }
  }, [open])

  const run = async (key: string, fn: () => void) => {
    setBusy(key)
    setMsg(null)
    try {
      fn()
      setMsg(`${key} sent`)
    } catch {
      setMsg(`${key} failed`)
    } finally {
      setBusy(null)
    }
  }

  const applyDisplay = () => {
    const next: Record<string, number> = {}
    const w = Number(pw)
    const h = Number(ph)
    const dpi = Number(pdpi)
    if (w > 0) next.projectionWidth = w
    if (h > 0) next.projectionHeight = h
    if (dpi >= 0) next.projectionDpi = dpi
    // Keep the main screen in sync with the projection tier (portrait panel:
    // they match). Allows a panel swap to be a settings change (§12.1).
    if (w > 0) next.mainScreenWidth = w
    if (h > 0) next.mainScreenHeight = h
    if (Object.keys(next).length === 0) {
      setMsg('No display values to apply')
      return
    }
    void run('Display', () => intent({ type: 'settings.set', settings: next }))
  }

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      slotProps={{
        paper: {
          sx: {
            width: 'min(420px, 92vw)',
            backgroundColor: t.surface,
            color: t.text,
            padding: '1rem 1.25rem 2rem',
            overflowY: 'auto'
          }
        }
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <SettingsIcon />
          <Typography sx={{ fontSize: '1.1rem', fontWeight: 500 }}>Settings</Typography>
        </Box>
        <IconButton onClick={onClose} size="small" sx={{ color: t.text }}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </Box>
      <Divider sx={{ borderColor: t.border, marginBottom: '0.5rem' }} />

      {msg && (
        <Typography sx={{ fontSize: '0.8rem', color: '#58a6ff', marginBottom: '0.5rem' }}>{msg}</Typography>
      )}

      <SectionTitle>Phone</SectionTitle>
      {projectingPhone ? (
        <Row
          icon={<DeleteIcon />}
          title={`Forget ${projectingPhone.person?.name ?? 'phone'}`}
          subtitle="Unpairs Bluetooth and removes the phone from the hub. Re-dock to re-enrol."
          danger
          action={
            <Button
              size="small"
              color="error"
              variant="outlined"
              disabled={busy === 'Forget'}
              onClick={() => run('Forget', () => intent({ type: 'phone.forget', phoneId: projectingPhone.phoneId }))}
            >
              Forget
            </Button>
          }
        />
      ) : (
        <Typography sx={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.5)', padding: '0.5rem 0' }}>
          No phone is projecting. Dock a phone to manage it.
        </Typography>
      )}
      {phones.length > 1 && (
        <Typography sx={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)' }}>
          {phones.length} phones known · forget is available for the projecting phone above.
        </Typography>
      )}

      <SectionTitle>Calibration</SectionTitle>
      <Row
        icon={<TuneIcon />}
        title="Reset calibration"
        subtitle="Clears recorded app positions for the projecting phone. Tiles will prompt for re-calibration."
        action={
          <Button
            size="small"
            variant="outlined"
            disabled={!projectingPhone || busy === 'Reset'}
            onClick={() => run('Reset', onResetCalibration)}
          >
            Reset
          </Button>
        }
      />

      <SectionTitle>System</SectionTitle>
      <Row
        icon={<RestartAltIcon />}
        title="Restart LIVI"
        subtitle="Restarts the LIVI kiosk (cage + Electron). AA sessions drop and re-establish on restart."
        action={
          <Button
            size="small"
            variant="outlined"
            disabled={busy === 'Restart'}
            onClick={() => run('Restart', () => intent({ type: 'system.restartLivi' }))}
          >
            Restart
          </Button>
        }
      />

      <SectionTitle>Display</SectionTitle>
      <Typography sx={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.55)', marginBottom: '0.5rem' }}>
        Projection tier dimensions + DPI. Must match the physical panel (e.g. 600×1024 portrait, 120 DPI).
        A change restarts the AA session at the new resolution.
      </Typography>
      <Box sx={{ display: 'flex', gap: '0.75rem', marginBottom: '0.75rem', flexWrap: 'wrap' }}>
        <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.75rem', color: 'rgba(255,255,255,0.6)' }}>
          Width
          <input
            type="number"
            value={pw}
            onChange={(e) => setPw(e.target.value)}
            style={inputStyle}
          />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.75rem', color: 'rgba(255,255,255,0.6)' }}>
          Height
          <input
            type="number"
            value={ph}
            onChange={(e) => setPh(e.target.value)}
            style={inputStyle}
          />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.75rem', color: 'rgba(255,255,255,0.6)' }}>
          DPI
          <input
            type="number"
            value={pdpi}
            onChange={(e) => setPdpi(e.target.value)}
            style={inputStyle}
          />
        </label>
      </Box>
      <Button size="small" variant="contained" onClick={applyDisplay} disabled={busy === 'Display'}>
        Apply display settings
      </Button>

      <SectionTitle>Network & services</SectionTitle>
      {netErr && (
        <Typography sx={{ fontSize: '0.75rem', color: '#ff6b6b' }}>
          Recovery server unreachable: {netErr}
        </Typography>
      )}
      {net && (
        <Box sx={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.75)', lineHeight: 1.6 }}>
          <Box>wlan0: <b>{net.wlan0?.operstate ?? '?'}</b>{net.wlan0?.carrier === false ? ' (no carrier)' : ''}</Box>
          <Box>gateway: <b>{net.gateway ?? '—'}</b></Box>
          <Box>livi-kiosk: <b>{net['livi-kiosk'] ?? '?'}</b></Box>
          <Box>hubd: <b>{net.hubd ?? '?'}</b></Box>
          <Box>watchdog: <b>{net['wlan0-watchdog'] ?? '?'}</b></Box>
        </Box>
      )}
      {!net && !netErr && (
        <Typography sx={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)' }}>Loading…</Typography>
      )}
      <Typography sx={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)', marginTop: '0.5rem' }}>
        Recovery console: http://10.0.0.123:8125/
      </Typography>
    </Drawer>
  )
}

const inputStyle: CSSProperties = {
  width: '5rem',
  backgroundColor: 'rgba(255,255,255,0.06)',
  border: '1px solid rgba(255,255,255,0.15)',
  color: '#fff',
  borderRadius: '6px',
  padding: '0.35rem 0.5rem',
  fontSize: '0.9rem',
  marginTop: '0.2rem'
}
