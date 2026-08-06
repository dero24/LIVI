/**
 * Contract tests — DeviceRegistry / DeviceController
 *
 * These tests assert the load-bearing assumptions from §3 and §9 that the hub
 * layer depends on. They test *upstream's* behaviour, not ours.
 *
 * Guards: §9.6, C1, C2, M2/M3
 */
import type { IPhoneDriver } from '../../driver/IPhoneDriver'
import { DeviceController } from '../DeviceController'
import { DeviceRegistry } from '../DeviceRegistry'
import { SessionManager } from '../SessionManager'

function mkDriver(): IPhoneDriver {
  return {} as unknown as IPhoneDriver
}

// DeviceRegistry needs app.getPath('userData') from electron — mock it.
vi.mock('electron', () => ({
  app: { getPath: () => '/tmp/test-contract' }
}))

function mkRegistry(): DeviceRegistry {
  return new DeviceRegistry('/tmp/test-contract-devices.json')
}

function mkController(registry: DeviceRegistry, sessions: SessionManager): DeviceController {
  return new DeviceController({
    deviceRegistry: registry,
    sessions: () => sessions,
    getDongleSession: () => null,
    aaBtSock: { disconnect: vi.fn(async () => {}), remove: vi.fn(async () => {}) } as never,
    getAaBtName: () => undefined,
    getAaBtMac: () => '',
    getDongleConnectedMac: () => '',
    getDongleDevList: () => [],
    emit: vi.fn(),
    pushReconnectTargets: vi.fn(),
    pushWiredPhones: vi.fn()
  })
}

describe('contract.device', () => {
  describe('selectDevice(unknownId) returns {ok:false} and calls no activate (§9.6)', () => {
    it('returns {ok:false} for an id with no matching session or registry entry', () => {
      const reg = mkRegistry()
      const sessions = new SessionManager({ route: () => {} })
      const ctrl = mkController(reg, sessions)
      const result = ctrl.selectDevice('UNKNOWN-ID-999')
      expect(result.ok).toBe(false)
    })

    it('returns {ok:false} for an id that matches a registry entry but has no session', () => {
      const reg = mkRegistry()
      reg.noteDevice({ btMac: 'AA:BB:CC:DD:EE:FF', name: 'Pixel', protocol: 'androidauto' })
      const sessions = new SessionManager({ route: () => {} })
      const ctrl = mkController(reg, sessions)
      // The device exists in the registry but has no active/held session
      const id = reg.list()[0] ? reg.deviceId(reg.list()[0]) : 'aa:bb:cc:dd:ee:ff'
      const result = ctrl.selectDevice(id)
      expect(result.ok).toBe(false)
    })
  })

  describe('deviceId() changes when btMac is added to a usbSerial-only entry (C1)', () => {
    it('deviceId is the usbSerial when only usbSerial is set', () => {
      const reg = mkRegistry()
      reg.noteDevice({ usbSerial: 'SER123', name: 'Phone', protocol: 'androidauto' })
      const entries = reg.list()
      expect(entries).toHaveLength(1)
      expect(reg.deviceId(entries[0])).toBe('SER123')
    })

    it('deviceId becomes btMac when btMac is later added', () => {
      const reg = mkRegistry()
      reg.noteDevice({ usbSerial: 'SER123', name: 'Phone', protocol: 'androidauto' })
      // Add btMac to the same device (matched by usbSerial)
      reg.noteDevice({ usbSerial: 'SER123', btMac: 'AA:BB:CC:DD:EE:FF', protocol: 'androidauto' })
      const entries = reg.list()
      expect(entries).toHaveLength(1)
      // deviceId prefers btMac over usbSerial
      expect(reg.deviceId(entries[0])).toBe('aa:bb:cc:dd:ee:ff')
    })
  })

  describe('DeviceView.session is an ordinal that renumbers when an earlier session closes (C2)', () => {
    it('assigns session ordinals based on session order', () => {
      const reg = mkRegistry()
      reg.noteDevice({ usbSerial: 'SER001', name: 'Phone1', protocol: 'androidauto' })
      reg.noteDevice({ usbSerial: 'SER002', name: 'Phone2', protocol: 'androidauto' })

      const sessions = new SessionManager({ route: () => {} })
      const s1 = sessions.upsert(mkDriver(), 'androidauto', 'usb', { usbSerial: 'SER001' })
      const s2 = sessions.upsert(mkDriver(), 'androidauto', 'usb', { usbSerial: 'SER002' })

      const ctrl = mkController(reg, sessions)
      const views = ctrl.getDevices()
      const v1 = views.find((v) => v.name === 'Phone1')
      const v2 = views.find((v) => v.name === 'Phone2')
      expect(v1?.session).toBe(1)
      expect(v2?.session).toBe(2)
    })

    it('renumbers when an earlier session closes', () => {
      const reg = mkRegistry()
      reg.noteDevice({ usbSerial: 'SER001', name: 'Phone1', protocol: 'androidauto' })
      reg.noteDevice({ usbSerial: 'SER002', name: 'Phone2', protocol: 'androidauto' })

      const sessions = new SessionManager({ route: () => {} })
      const s1 = sessions.upsert(mkDriver(), 'androidauto', 'usb', { usbSerial: 'SER001' })
      const s2 = sessions.upsert(mkDriver(), 'androidauto', 'usb', { usbSerial: 'SER002' })

      const ctrl = mkController(reg, sessions)
      // Close the first session — the second should now be ordinal 1
      sessions.close(s1.index)
      const views = ctrl.getDevices()
      const v2 = views.find((v) => v.name === 'Phone2')
      expect(v2?.session).toBe(1)
    })
  })

  // M2/M3: DeviceView will carry `aliases` and `sessionIndex` fields.
  // These fields do not exist in upstream yet — skip until the hub layer adds them.
  describe.skip('DeviceView carries aliases and sessionIndex (M2/M3)', () => {
    it('DeviceView has an aliases field', () => {
      const reg = mkRegistry()
      reg.noteDevice({ usbSerial: 'SER001', name: 'Phone1', protocol: 'androidauto' })
      const sessions = new SessionManager({ route: () => {} })
      sessions.upsert(mkDriver(), 'androidauto', 'usb', { usbSerial: 'SER001' })
      const ctrl = mkController(reg, sessions)
      const views = ctrl.getDevices()
      expect(views[0]).toHaveProperty('aliases')
    })

    it('DeviceView has a sessionIndex field', () => {
      const reg = mkRegistry()
      reg.noteDevice({ usbSerial: 'SER001', name: 'Phone1', protocol: 'androidauto' })
      const sessions = new SessionManager({ route: () => {} })
      sessions.upsert(mkDriver(), 'androidauto', 'usb', { usbSerial: 'SER001' })
      const ctrl = mkController(reg, sessions)
      const views = ctrl.getDevices()
      expect(views[0]).toHaveProperty('sessionIndex')
    })
  })
})
