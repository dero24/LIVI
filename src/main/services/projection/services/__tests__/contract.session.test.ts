/**
 * Contract tests — SessionManager
 *
 * These tests assert the load-bearing assumptions from §3 (session lifecycle,
 * identity, promotion) that the hub layer depends on. They test *upstream's*
 * behaviour, not ours. A red contract test means §3 has changed and the plan
 * must be amended before the code.
 *
 * Guards: §3.2, Rule 3 L1, §8.4 L1, D1
 */
import type { IPhoneDriver } from '../../driver/IPhoneDriver'
import { SessionManager } from '../SessionManager'
import type { SessionDeviceIds } from '../SessionManager'

function mkDriver(): IPhoneDriver {
  return {} as unknown as IPhoneDriver
}

function mkManager(): SessionManager {
  return new SessionManager({ route: () => {} })
}

describe('contract.session', () => {
  describe('upsert() returns a session with state === "held"', () => {
    it('creates a new session in the held state (§3.2, Rule 3 L1)', () => {
      const mgr = mkManager()
      const s = mgr.upsert(mkDriver(), 'androidauto', 'usb', { usbSerial: 'SER001' })
      expect(s.state).toBe('held')
      expect(s.protocol).toBe('androidauto')
      expect(s.transport).toBe('usb')
    })

    it('never auto-activates on upsert alone', () => {
      const mgr = mkManager()
      mgr.upsert(mkDriver(), 'carplay', 'usb', { usbUdid: 'UDID-1' })
      expect(mgr.active()).toBeNull()
    })
  })

  describe('maybeAutoActivate promotes only when active() is null (§8.4 L1)', () => {
    // maybeAutoActivate is a private method on ProjectionService, but its
    // contract is simple: it calls sessions.activate(s.index) only when
    // sessions.active() returns null. We test the observable effect through
    // SessionManager.activate() which is the mechanism it uses.
    it('activate() promotes a held session to active', () => {
      const mgr = mkManager()
      const s = mgr.upsert(mkDriver(), 'androidauto', 'usb', { usbSerial: 'SER001' })
      expect(mgr.active()).toBeNull()
      mgr.activate(s.index)
      expect(mgr.active()).toBe(s)
      expect(s.state).toBe('active')
    })

    it('activate() demotes the previous active session to held', () => {
      const mgr = mkManager()
      const s1 = mgr.upsert(mkDriver(), 'androidauto', 'usb', { usbSerial: 'SER001' })
      const s2 = mgr.upsert(mkDriver(), 'carplay', 'usb', { usbUdid: 'UDID-2' })
      mgr.activate(s1.index)
      expect(s1.state).toBe('active')
      mgr.activate(s2.index)
      expect(s2.state).toBe('active')
      expect(s1.state).toBe('held')
    })
  })

  describe('closing the active session promotes a held one (§3.2)', () => {
    it('promotes the first held session when the active session closes', () => {
      const mgr = mkManager()
      const s1 = mgr.upsert(mkDriver(), 'androidauto', 'usb', { usbSerial: 'SER001' })
      const s2 = mgr.upsert(mkDriver(), 'carplay', 'usb', { usbUdid: 'UDID-2' })
      mgr.activate(s1.index)
      expect(mgr.active()).toBe(s1)

      mgr.close(s1.index)
      expect(mgr.active()).toBe(s2)
      expect(s2.state).toBe('active')
    })

    it('leaves no active session when the last session closes', () => {
      const mgr = mkManager()
      const s = mgr.upsert(mkDriver(), 'androidauto', 'usb', { usbSerial: 'SER001' })
      mgr.activate(s.index)
      mgr.close(s.index)
      expect(mgr.active()).toBeNull()
    })

    it('does not promote when a held (non-active) session closes', () => {
      const mgr = mkManager()
      const s1 = mgr.upsert(mkDriver(), 'androidauto', 'usb', { usbSerial: 'SER001' })
      const s2 = mgr.upsert(mkDriver(), 'carplay', 'usb', { usbUdid: 'UDID-2' })
      mgr.activate(s1.index)
      mgr.close(s2.index)
      expect(mgr.active()).toBe(s1)
      expect(mgr.all()).toHaveLength(1)
    })
  })

  describe('idsOverlap matches on any single id and lower-cases MACs (D1)', () => {
    // idsOverlap is a module-private function; we exercise it through
    // byIdentity / byDevice which are the public surfaces that use it.
    it('matches sessions by btMac case-insensitively', () => {
      const mgr = mkManager()
      const s = mgr.upsert(mkDriver(), 'carplay', 'bt', { btMac: 'AA:BB:CC:DD:EE:FF' })
      expect(mgr.byDevice({ btMac: 'aa:bb:cc:dd:ee:ff' })).toBe(s)
      expect(mgr.byDevice({ btMac: 'AA:BB:CC:DD:EE:FF' })).toBe(s)
    })

    it('matches sessions by usbSerial', () => {
      const mgr = mkManager()
      const s = mgr.upsert(mkDriver(), 'androidauto', 'usb', { usbSerial: 'SER123' })
      expect(mgr.byDevice({ usbSerial: 'SER123' })).toBe(s)
    })

    it('matches sessions by instanceId', () => {
      const mgr = mkManager()
      const s = mgr.upsert(mkDriver(), 'androidauto', 'wifi', { instanceId: 'inst-1' })
      expect(mgr.byDevice({ instanceId: 'inst-1' })).toBe(s)
    })

    it('does not match when no ids overlap', () => {
      const mgr = mkManager()
      mgr.upsert(mkDriver(), 'androidauto', 'usb', { usbSerial: 'SER123' })
      expect(mgr.byDevice({ usbSerial: 'SER999' })).toBeNull()
    })
  })

  describe('sticky merge: "" and undefined never erase a known alias (D1)', () => {
    it('undefined does not erase a known btMac', () => {
      const mgr = mkManager()
      const driver = mkDriver()
      const s = mgr.upsert(driver, 'androidauto', 'wifi', { btMac: 'AA:BB:CC:DD:EE:FF' })
      mgr.upsert(driver, 'androidauto', 'wifi', { btMac: undefined, instanceId: 'inst-1' })
      expect(s.device.btMac).toBe('aa:bb:cc:dd:ee:ff')
      expect(s.device.instanceId).toBe('inst-1')
    })

    it('empty string does not erase a known usbUdid', () => {
      const mgr = mkManager()
      const driver = mkDriver()
      const s = mgr.upsert(driver, 'carplay', 'wifi', { usbUdid: '00008120-DEADBEEF' })
      mgr.upsert(driver, 'carplay', 'wifi', { usbUdid: '', ip: '172.20.10.1' })
      expect(s.device.usbUdid).toBe('00008120-DEADBEEF')
      expect(s.device.ip).toBe('172.20.10.1')
    })
  })
})
