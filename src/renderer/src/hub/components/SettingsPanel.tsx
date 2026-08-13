// [hub] §12.5: the settings panel — a right-anchored drawer opened from the
// gear in the bar. It is the human surface for the intents hubd already owns
// (§7.5): forget a phone, reset calibration, restart LIVI, and inspect
// network/service health. Per the plan it is a node in LIVI's own settings
// surface — here a lightweight MUI Drawer rather than the full schema tree,
// since the hub only owns a handful of keys (SETTINGS_ALLOWLIST in
// hubd/hubd/intents.py). Every write goes through `window.hub.intent` so hubd
// remains the single mutation path (D7).
import { Box, Button, Divider, Drawer, IconButton, Typography } from '@mui/material'
import SettingsIcon from '@mui/icons-material/Settings'
import CloseIcon from '@mui/icons-material/Close'
import RestartAltIcon from '@mui/icons-material/RestartAlt'
import TuneIcon from '@mui/icons-material/Tune'
import { type ReactNode, useEffect, useState } from 'react'
import type { HubPhone } from '../types'
import { useHubTokens } from '../useHubTokens'
import { isCalibrated, LANDING_TILES } from './Landing'

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
  onResetCalibration,
  onRecalibrateApp
}: SettingsPanelProps) {
  const t = useHubTokens()
  const [net, setNet] = useState<NetStatus | null>(null)
  const [netErr, setNetErr] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)

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

      <SectionTitle>Phones</SectionTitle>
      {phones.length === 0 ? (
        <Typography sx={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.5)', padding: '0.5rem 0' }}>
          No phones known. Dock a phone to begin.
        </Typography>
      ) : (
        phones.map((p) => (
          <Box key={p.phoneId} sx={{ marginBottom: '0.5rem' }}>
            <Row
              icon={
                <Box sx={{
                  width: '1.5rem', height: '1.5rem', borderRadius: '50%',
                  backgroundColor: p.person?.colour ?? '#4F7CAC',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  color: '#fff', fontSize: '0.7rem', fontWeight: 600
                }}>
                  {(p.person?.name ?? 'P').charAt(0).toUpperCase()}
                </Box>
              }
              title={p.person?.name ?? 'Unknown'}
              subtitle={`${p.presence.level}${p.livi?.batteryLevel != null ? ` · ${p.livi.batteryLevel}%` : ''}`}
              action={
                p.presence.level === 'projecting' ? (
                  <Button
                    size="small"
                    color="error"
                    variant="outlined"
                    disabled={busy === 'Forget'}
                    onClick={() => run('Forget', () => intent({ type: 'phone.forget', phoneId: p.phoneId }))}
                  >
                    Forget
                  </Button>
                ) : (
                  <Typography sx={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)' }}>
                    {p.presence.level === 'absent' ? 'Away' : 'Dock to manage'}
                  </Typography>
                )
              }
            />
          </Box>
        ))
      )}

      <SectionTitle>Calibration</SectionTitle>
      {phones.filter((p) => p.presence.rank >= 2).length === 0 ? (
        <Typography sx={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.5)', padding: '0.5rem 0' }}>
          No phones present. Dock a phone to calibrate.
        </Typography>
      ) : (
        <Box sx={{ marginBottom: '0.5rem' }}>
          {phones.filter((p) => p.presence.rank >= 2).map((p) => {
            const isProjecting = p.presence.level === 'projecting'
            return (
              <Box key={p.phoneId} sx={{ marginBottom: '0.75rem' }}>
                <Typography sx={{ fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.25rem' }}>
                  {p.person?.name ?? 'Unknown'}
                  {!isProjecting && <Box component="span" sx={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)', marginLeft: '0.5rem' }}>(dock & project to recalibrate)</Box>}
                </Typography>
                {LANDING_TILES.filter((t) => t.calibratable).map((tile) => {
                  const calibrated = isCalibrated(p.phoneId, tile.key)
                  return (
                    <Box key={tile.key} sx={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.25rem 0' }}>
                      <Box sx={{ fontSize: '1.1rem' }}>{tile.icon}</Box>
                      <Box sx={{ flex: 1 }}>
                        <Typography sx={{ fontSize: '0.8rem' }}>{tile.label}</Typography>
                        <Typography sx={{ fontSize: '0.7rem', color: calibrated ? '#58a6ff' : 'rgba(255,255,255,0.4)' }}>
                          {calibrated ? 'Calibrated' : 'Not calibrated'}
                        </Typography>
                      </Box>
                      <Button
                        size="small"
                        variant="outlined"
                        disabled={!isProjecting}
                        onClick={() => onRecalibrateApp?.(p.phoneId, tile.key)}
                      >
                        Recalibrate
                      </Button>
                    </Box>
                  )
                })}
              </Box>
            )
          })}
          {projectingPhone && (
            <Row
              icon={<TuneIcon />}
              title="Reset all calibration"
              subtitle={`Clears all recorded app positions for ${projectingPhone.person?.name ?? 'the projecting phone'}.`}
              action={
                <Button
                  size="small"
                  variant="outlined"
                  disabled={busy === 'Reset'}
                  onClick={() => run('Reset', onResetCalibration)}
                >
                  Reset
                </Button>
              }
            />
          )}
        </Box>
      )}

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
