/**
 * Contract tests — TransportArbiter
 *
 * These tests assert the transport selection contract from §3.3 and C5.
 * They test *upstream's* behaviour, not ours.
 *
 * Guards: C5, §3.3
 */
import type { Device } from 'usb'
import type { Mock } from 'vitest'
import { TransportArbiter } from '../TransportArbiter'
import type { ArbiterDeps, Transport } from '../types'

type DepStubs = {
  wirelessAaEnabled: boolean
  wirelessPhoneInRange: boolean
  active: Transport | null
  dongleSessionActive: boolean
  wiredAaSessionActive: boolean
  wiredCpSessionActive: boolean
  wiredSession: boolean
  onChange: Mock
  onShouldStop: Mock
  onShouldAutoStart: Mock
  onShouldBringUpWiredBeside: Mock
  onWiredPhoneGone: Mock
}

function makeArbiter(overrides: Partial<DepStubs> = {}) {
  const stubs: DepStubs = {
    wirelessAaEnabled: false,
    wirelessPhoneInRange: false,
    active: null,
    dongleSessionActive: false,
    wiredAaSessionActive: false,
    wiredCpSessionActive: false,
    wiredSession: false,
    onChange: vi.fn(),
    onShouldStop: vi.fn(async () => {}),
    onShouldAutoStart: vi.fn(),
    onShouldBringUpWiredBeside: vi.fn(),
    onWiredPhoneGone: vi.fn(),
    ...overrides
  }
  const deps: ArbiterDeps = {
    isWirelessEnabled: () => stubs.wirelessAaEnabled,
    isWirelessPhoneInRange: () => stubs.wirelessPhoneInRange,
    getActiveTransport: () => stubs.active,
    isDongleSessionActive: () => stubs.dongleSessionActive,
    isWiredAaSessionActive: () => stubs.wiredAaSessionActive,
    isWiredCpSessionActive: () => stubs.wiredCpSessionActive,
    hasWiredSession: () => stubs.wiredSession,
    onChange: stubs.onChange,
    onShouldStop: stubs.onShouldStop,
    onShouldAutoStart: stubs.onShouldAutoStart,
    onShouldBringUpWiredBeside: stubs.onShouldBringUpWiredBeside,
    onWiredPhoneGone: stubs.onWiredPhoneGone
  }
  return { arbiter: new TransportArbiter(deps), stubs }
}

function appleDevice(): Device {
  return { deviceDescriptor: { idVendor: 0x05ac, idProduct: 0x1234 } } as unknown as Device
}

function androidDevice(): Device {
  return { deviceDescriptor: { idVendor: 0x18d1, idProduct: 0x4ee1 } } as unknown as Device
}

describe('contract.transport', () => {
  describe('wantCp === true on Linux with no dongle (C5)', () => {
    // wantCp is a local variable in ProjectionService.syncHelperSupervisor():
    //   const wantCp = linux
    // This means wired CarPlay is always live on Linux. We verify the
    // transport arbiter side: a wired Apple phone selects cp:wired even
    // when no dongle is present.
    it('an Apple phone on USB selects cp:wired with no dongle', () => {
      const { arbiter } = makeArbiter()
      arbiter.markPhoneConnected(true, appleDevice())
      const candidates = arbiter.detectedCandidates()
      expect(candidates).toContainEqual({ transport: 'cp', mode: 'wired' })
      expect(candidates).not.toContainEqual({ transport: 'aa', mode: 'wired' })
    })
  })

  describe('Apple vendor id 0x05ac selects cp:wired (§3.3)', () => {
    it('detects cp:wired for an Apple device', () => {
      const { arbiter } = makeArbiter()
      arbiter.markPhoneConnected(true, appleDevice())
      expect(arbiter.detectedCandidates()).toContainEqual({ transport: 'cp', mode: 'wired' })
    })

    it('detects aa:wired for a non-Apple device', () => {
      const { arbiter } = makeArbiter()
      arbiter.markPhoneConnected(true, androidDevice())
      expect(arbiter.detectedCandidates()).toContainEqual({ transport: 'aa', mode: 'wired' })
      expect(arbiter.detectedCandidates()).not.toContainEqual({ transport: 'cp', mode: 'wired' })
    })
  })

  describe('aa:wireless is offered when a wired AA session is active (§3.3)', () => {
    it('offers aa:wireless when wireless is enabled and a wired AA session is active', () => {
      const { arbiter } = makeArbiter({
        wirelessAaEnabled: true,
        wiredAaSessionActive: true,
        wirelessPhoneInRange: false
      })
      const candidates = arbiter.detectedCandidates()
      expect(candidates).toContainEqual({ transport: 'aa', mode: 'wireless' })
    })

    it('offers aa:wireless when wireless is enabled and a wireless phone is in range', () => {
      const { arbiter } = makeArbiter({
        wirelessAaEnabled: true,
        wirelessPhoneInRange: true
      })
      const candidates = arbiter.detectedCandidates()
      expect(candidates).toContainEqual({ transport: 'aa', mode: 'wireless' })
    })

    it('does not offer aa:wireless when wireless is disabled', () => {
      const { arbiter } = makeArbiter({
        wirelessAaEnabled: false,
        wiredAaSessionActive: true,
        wirelessPhoneInRange: true
      })
      const candidates = arbiter.detectedCandidates()
      expect(candidates).not.toContainEqual({ transport: 'aa', mode: 'wireless' })
    })

    it('does not offer aa:wireless when wireless is enabled but no phone in range and no wired AA session', () => {
      const { arbiter } = makeArbiter({
        wirelessAaEnabled: true,
        wirelessPhoneInRange: false,
        wiredAaSessionActive: false
      })
      const candidates = arbiter.detectedCandidates()
      expect(candidates).not.toContainEqual({ transport: 'aa', mode: 'wireless' })
    })
  })
})
