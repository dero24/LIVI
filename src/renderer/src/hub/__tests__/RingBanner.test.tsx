import { createTheme, ThemeProvider } from '@mui/material/styles'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { RingBanner } from '../components/RingBanner'
import type { HubRing } from '../types'

function mkRing(overrides: Partial<HubRing> = {}): HubRing {
  return {
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
    queued: [],
    ...overrides
  }
}

function renderBanner(ring: HubRing, knownPhoneCount = 2) {
  return render(
    <ThemeProvider theme={createTheme({ palette: { mode: 'dark' } })}>
      <RingBanner ring={ring} knownPhoneCount={knownPhoneCount} />
    </ThemeProvider>
  )
}

describe('RingBanner', () => {
  it('shows the caller name as the largest text and "calling <person>" when >1 phone', () => {
    renderBanner(mkRing(), 2)
    expect(screen.getByText('Mom')).toBeInTheDocument()
    expect(screen.getByText(/calling Sarah/i)).toBeInTheDocument()
  })

  it('omits "calling <person>" with a single known phone (redundancy is noise)', () => {
    renderBanner(mkRing(), 1)
    expect(screen.queryByText(/calling Sarah/i)).not.toBeInTheDocument()
  })

  it('falls back to "Incoming call" when no caller identity yet (progressive)', () => {
    renderBanner(mkRing({ caller: { name: null, number: null, photo: null } }), 1)
    expect(screen.getByText('Incoming call')).toBeInTheDocument()
  })

  it('shows Answer when canAnswerOnHub, "Answer on phone" when not', () => {
    const { rerender } = renderBanner(mkRing({ canAnswerOnHub: true }))
    expect(screen.getByTestId('hub-ring-answer').textContent).toBe('Answer')
    rerender(
      <ThemeProvider theme={createTheme({ palette: { mode: 'dark' } })}>
        <RingBanner
          ring={mkRing({ canAnswerOnHub: false, answerVia: 'companion' })}
          knownPhoneCount={2}
        />
      </ThemeProvider>
    )
    expect(screen.getByTestId('hub-ring-answer').textContent).toBe('Answer on phone')
  })

  it('shows [Bring to hub] only when canBringToHub is true', () => {
    const { rerender } = renderBanner(mkRing({ canBringToHub: false }))
    expect(screen.queryByTestId('hub-ring-bring-to-hub')).not.toBeInTheDocument()
    rerender(
      <ThemeProvider theme={createTheme({ palette: { mode: 'dark' } })}>
        <RingBanner ring={mkRing({ canBringToHub: true })} knownPhoneCount={2} />
      </ThemeProvider>
    )
    expect(screen.getByTestId('hub-ring-bring-to-hub')).toBeInTheDocument()
  })

  it('shows Silence only while the tone is active', () => {
    renderBanner(mkRing({ tone: true }))
    expect(screen.getByTestId('hub-ring-silence')).toBeInTheDocument()
  })

  it('hides Silence when the tone was suppressed (DND/starred)', () => {
    renderBanner(mkRing({ tone: false }))
    expect(screen.queryByTestId('hub-ring-silence')).not.toBeInTheDocument()
  })

  it('renders the queued "also:" row for a second ringing phone', () => {
    renderBanner(
      mkRing({
        queued: [
          {
            phoneId: 'P2',
            person: 'Robby',
            caller: { name: 'Dad', number: null, photo: null },
            state: 'incoming',
            tier: 1
          }
        ]
      })
    )
    expect(screen.getByText(/also: Robby/i)).toBeInTheDocument()
  })

  it('fires onAnswer/onDecline/onSilence/onBringToHub with the phoneId', () => {
    const onAnswer = vi.fn()
    const onDecline = vi.fn()
    const onSilence = vi.fn()
    const onBringToHub = vi.fn()
    render(
      <ThemeProvider theme={createTheme({ palette: { mode: 'dark' } })}>
        <RingBanner
          ring={mkRing({ canBringToHub: true })}
          knownPhoneCount={2}
          onAnswer={onAnswer}
          onDecline={onDecline}
          onSilence={onSilence}
          onBringToHub={onBringToHub}
        />
      </ThemeProvider>
    )
    fireEvent.click(screen.getByTestId('hub-ring-answer'))
    expect(onAnswer).toHaveBeenCalledWith('P1')
    fireEvent.click(screen.getByTestId('hub-ring-decline'))
    expect(onDecline).toHaveBeenCalledWith('P1')
    fireEvent.click(screen.getByTestId('hub-ring-silence'))
    expect(onSilence).toHaveBeenCalledWith('P1')
    fireEvent.click(screen.getByTestId('hub-ring-bring-to-hub'))
    expect(onBringToHub).toHaveBeenCalledWith('P1')
  })
})
