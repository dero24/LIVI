import { createTheme, ThemeProvider } from '@mui/material/styles'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { HubShell } from '../HubShell'
import type { HubState } from '../types'

function mkState(overrides: Partial<HubState> = {}): HubState {
  return {
    v: 1,
    rev: 1,
    at: new Date().toISOString(),
    phones: [],
    docks: [],
    transport: null,
    health: { ok: true, bridge: true },
    ...overrides
  }
}

function installHub(state: HubState | null) {
  const intent = vi.fn(async () => ({ ok: true }))
  const listeners = new Set<(s: HubState) => void>()
  window.hub = {
    getState: async () => state,
    onState: (cb) => {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    intent
  }
  return { intent, push: (s: HubState) => listeners.forEach((l) => l(s)) }
}

function renderShell(mode: 'light' | 'dark' = 'dark') {
  return render(
    <ThemeProvider theme={createTheme({ palette: { mode } })}>
      <HubShell />
    </ThemeProvider>
  )
}

afterEach(() => {
  window.hub = undefined
  vi.restoreAllMocks()
})

describe('HubShell', () => {
  it('shows the screensaver with a prompt when no phones are known', async () => {
    installHub(mkState({ phones: [] }))
    renderShell()
    await waitFor(() => expect(screen.getByTestId('hub-screensaver')).toBeInTheDocument())
    expect(screen.getByText(/dock a phone to begin/i)).toBeInTheDocument()
  })

  it('renders a presence row with a bubble per phone', async () => {
    installHub(
      mkState({
        phones: [
          {
            phoneId: 'P1',
            person: { name: 'Pixel', colour: '#4F7CAC' },
            platform: 'android',
            protocol: 'androidauto',
            presence: { level: 'docked', rank: 3 },
            livi: { batteryLevel: 82 }
          },
          {
            phoneId: 'P2',
            person: { name: 'iPhone', colour: '#C97C5D' },
            platform: 'ios',
            protocol: 'carplay',
            presence: { level: 'absent', rank: 0 }
          }
        ]
      })
    )
    renderShell()
    await waitFor(() => expect(screen.getByTestId('hub-presence-row')).toBeInTheDocument())
    expect(screen.getAllByTestId('hub-phone-bubble')).toHaveLength(2)
    expect(screen.getByText('Pixel')).toBeInTheDocument()
    expect(screen.getByText(/82%/)).toBeInTheDocument()
    // 1 of 2 home summary
    expect(screen.getByText(/1 of 2 home/i)).toBeInTheDocument()
  })

  it('health dot is healthy when bridge is up and state is fresh', async () => {
    installHub(mkState({ phones: [], health: { ok: true, bridge: true } }))
    renderShell()
    await waitFor(() =>
      expect(screen.getByTestId('hub-health-dot')).toHaveAttribute('data-healthy', 'true')
    )
  })

  it('health dot goes unhealthy when the bridge is down', async () => {
    installHub(mkState({ phones: [], health: { ok: true, bridge: false } }))
    renderShell()
    await waitFor(() =>
      expect(screen.getByTestId('hub-health-dot')).toHaveAttribute('data-healthy', 'false')
    )
  })

  it('tapping a phone bubble posts a phone.select intent', async () => {
    const { intent } = installHub(
      mkState({
        phones: [
          {
            phoneId: 'P1',
            person: { name: 'Pixel' },
            platform: 'android',
            protocol: 'androidauto',
            presence: { level: 'docked', rank: 3 }
          }
        ]
      })
    )
    renderShell()
    await waitFor(() => expect(screen.getByTestId('hub-phone-bubble')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('hub-phone-bubble'))
    expect(intent).toHaveBeenCalledWith({ type: 'phone.select', phoneId: 'P1' })
  })

  it('renders in light mode without error', async () => {
    installHub(mkState({ phones: [] }))
    renderShell('light')
    await waitFor(() => expect(screen.getByTestId('hub-shell')).toBeInTheDocument())
  })

  it('overlays the ring banner when HubState.ring is set and wires intents', async () => {
    const { intent } = installHub(
      mkState({
        phones: [
          {
            phoneId: 'P1',
            person: { name: 'Sarah' },
            platform: 'android',
            protocol: 'androidauto',
            presence: { level: 'projecting', rank: 4 }
          }
        ],
        ring: {
          phoneId: 'P1',
          person: 'Sarah',
          caller: { name: 'Mom', number: '+15551234', photo: null },
          state: 'incoming',
          tier: 1,
          tone: true,
          startedAt: Date.now(),
          canAnswerOnHub: true,
          answerVia: 'projection',
          canBringToHub: true,
          queued: []
        }
      })
    )
    renderShell()
    await waitFor(() => expect(screen.getByTestId('hub-ring-banner')).toBeInTheDocument())
    expect(screen.getByText('Mom')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('hub-ring-answer'))
    expect(intent).toHaveBeenCalledWith({ type: 'ring.answer', phoneId: 'P1' })
    fireEvent.click(screen.getByTestId('hub-ring-bring-to-hub'))
    expect(intent).toHaveBeenCalledWith({ type: 'ring.bringToHub', phoneId: 'P1' })
  })

  it('shows screensaver by default when a phone is projecting (Phase 1.10)', async () => {
    installHub(
      mkState({
        phones: [
          {
            phoneId: 'P1',
            person: { name: 'Pixel', colour: '#4F7CAC' },
            platform: 'android',
            protocol: 'androidauto',
            presence: { level: 'projecting', rank: 4 },
            livi: { batteryLevel: 82 }
          }
        ]
      })
    )
    renderShell()
    await waitFor(() => expect(screen.getByTestId('hub-presence-row')).toBeInTheDocument())
    const shell = screen.getByTestId('hub-shell')
    // Phase 1.10: default viewMode is 'screensaver' — opaque background,
    // screensaver visible with bubbles, landing page NOT shown.
    expect(shell).not.toHaveStyle({ backgroundColor: 'rgba(0, 0, 0, 0)' })
    expect(screen.getByTestId('hub-screensaver')).toBeInTheDocument()
    expect(screen.queryByTestId('hub-landing')).not.toBeInTheDocument()
  })

  it('tapping a projecting phone bubble navigates to the landing page', async () => {
    installHub(
      mkState({
        phones: [
          {
            phoneId: 'P1',
            person: { name: 'Pixel', colour: '#4F7CAC' },
            platform: 'android',
            protocol: 'androidauto',
            presence: { level: 'projecting', rank: 4 },
            livi: { batteryLevel: 82 }
          }
        ]
      })
    )
    renderShell()
    await waitFor(() => expect(screen.getByTestId('hub-phone-bubble')).toBeInTheDocument())
    // Default is screensaver — no landing page
    expect(screen.queryByTestId('hub-landing')).not.toBeInTheDocument()
    // Tap the bubble → landing page appears
    fireEvent.click(screen.getByTestId('hub-phone-bubble'))
    await waitFor(() => expect(screen.getByTestId('hub-landing')).toBeInTheDocument())
  })

  it('back button cycles from landing to screensaver', async () => {
    installHub(
      mkState({
        phones: [
          {
            phoneId: 'P1',
            person: { name: 'Pixel', colour: '#4F7CAC' },
            platform: 'android',
            protocol: 'androidauto',
            presence: { level: 'projecting', rank: 4 },
            livi: { batteryLevel: 82 }
          }
        ]
      })
    )
    renderShell()
    await waitFor(() => expect(screen.getByTestId('hub-phone-bubble')).toBeInTheDocument())
    // Tap bubble → landing
    fireEvent.click(screen.getByTestId('hub-phone-bubble'))
    await waitFor(() => expect(screen.getByTestId('hub-landing')).toBeInTheDocument())
    // Back button → screensaver
    fireEvent.click(screen.getByTestId('hub-back-button'))
    await waitFor(() => expect(screen.queryByTestId('hub-landing')).not.toBeInTheDocument())
    expect(screen.getByTestId('hub-screensaver')).toBeInTheDocument()
  })

  it('shows the ring banner on top of the screensaver', async () => {
    const { intent } = installHub(
      mkState({
        phones: [
          {
            phoneId: 'P1',
            person: { name: 'Sarah' },
            platform: 'android',
            protocol: 'androidauto',
            presence: { level: 'docked', rank: 3 }
          }
        ],
        ring: {
          phoneId: 'P1',
          person: 'Sarah',
          caller: { name: 'Mom', number: '+15551234', photo: null },
          state: 'incoming',
          tier: 1,
          tone: true,
          startedAt: Date.now(),
          canAnswerOnHub: true,
          answerVia: 'projection',
          canBringToHub: false,
          queued: []
        }
      })
    )
    renderShell()
    await waitFor(() => expect(screen.getByTestId('hub-ring-banner')).toBeInTheDocument())
    // Ring banner is on top of the screensaver
    expect(screen.getByTestId('hub-screensaver')).toBeInTheDocument()
    expect(screen.getByText('Mom')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('hub-ring-answer'))
    expect(intent).toHaveBeenCalledWith({ type: 'ring.answer', phoneId: 'P1' })
  })

  it('gear icon is visible in all view modes (screensaver and landing)', async () => {
    installHub(
      mkState({
        phones: [
          {
            phoneId: 'P1',
            person: { name: 'Pixel', colour: '#4F7CAC' },
            platform: 'android',
            protocol: 'androidauto',
            presence: { level: 'projecting', rank: 4 },
            livi: { batteryLevel: 82 }
          }
        ]
      })
    )
    renderShell()
    await waitFor(() => expect(screen.getByTestId('hub-phone-bubble')).toBeInTheDocument())
    // Gear visible on screensaver
    expect(screen.getByTestId('hub-settings-gear')).toBeInTheDocument()
    // Tap bubble → landing page
    fireEvent.click(screen.getByTestId('hub-phone-bubble'))
    await waitFor(() => expect(screen.getByTestId('hub-landing')).toBeInTheDocument())
    // Gear still visible on landing page (was hidden by Landing's zIndex:5)
    expect(screen.getByTestId('hub-settings-gear')).toBeInTheDocument()
  })

  it('keeps the opaque background and greeting when phones are docked but not projecting', async () => {
    installHub(
      mkState({
        phones: [
          {
            phoneId: 'P1',
            person: { name: 'Pixel', colour: '#4F7CAC' },
            platform: 'android',
            protocol: 'androidauto',
            presence: { level: 'docked', rank: 3 },
            livi: { batteryLevel: 82 }
          }
        ]
      })
    )
    renderShell()
    await waitFor(() => expect(screen.getByTestId('hub-presence-row')).toBeInTheDocument())
    const shell = screen.getByTestId('hub-shell')
    // Root background must be the token bg (opaque) — no video to show through.
    expect(shell).not.toHaveStyle({ backgroundColor: 'transparent' })
    // The greeting text IS rendered.
    expect(screen.getByText(/good (morning|afternoon|evening)/i)).toBeInTheDocument()
  })
})
