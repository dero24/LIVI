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
})
