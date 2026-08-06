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
    // Upstream's deviceId() returns btMac ?? usbUdid ?? wifiMac ?? instanceId ?? ''
    // It does NOT include usbSerial in the priority chain. A usbSerial-only
    // entry therefore has deviceId === '' until a btMac (or usbUdid/wifiMac/
    // instanceId) is added. This is the instability C1 documents.
    it('deviceId is empty when only usbSerial is set', () => {
      const reg = mkRegistry()
      reg.noteDevice({ usbSerial: 'SER123', name: 'Phone', protocol: 'androidauto' })
      const entries = reg.list()
      expect(entries).toHaveLength(1)
      expect(reg.deviceId(entries[0])).toBe('')
    })

    it('deviceId becomes btMac when btMac is later added', () => {
      const reg = mkRegistry()
      reg.noteDevice({ usbSerial: 'SER123', name: 'Phone', protocol: 'androidauto' })
      // Add btMac to the same device (matched by usbSerial)
      reg.noteDevice({ usbSerial: 'SER123', btMac: 'AA:BB:CC:DD:EE:FF', protocol: 'androidauto' })
      const entries = reg.list()
      expect(entries).toHaveLength(1)
      // deviceId changes from '' to the btMac — this is the C1 instability
      expect(reg.deviceId(entries[0])).toBe('aa:bb:cc:dd:ee:ff')
    })
  })

  describe('DeviceView.session is an ordinal that renumbers when an earlier session closes (C2)', () => {
    // buildDeviceViews passes {btMac, wifiMac, usbUdid, instanceId, ip} to
    // byDevice — it does NOT pass usbSerial. Use instanceId so the match works.
    it('assigns session ordinals based on session order', () => {
      const reg = mkRegistry()
      reg.noteDevice({ instanceId: 'inst-1', name: 'Phone1', protocol: 'androidauto' })
      reg.noteDevice({ instanceId: 'inst-2', name: 'Phone2', protocol: 'androidauto' })

      const sessions = new SessionManager({ route: () => {} })
      sessions.upsert(mkDriver(), 'androidauto', 'usb', { instanceId: 'inst-1' })
      sessions.upsert(mkDriver(), 'androidauto', 'usb', { instanceId: 'inst-2' })

      const ctrl = mkController(reg, sessions)
      const views = ctrl.getDevices()
      const v1 = views.find((v) => v.name === 'Phone1')
      const v2 = views.find((v) => v.name === 'Phone2')
      expect(v1?.session).toBe(1)
      expect(v2?.session).toBe(2)
    })

    it('renumbers when an earlier session closes', () => {
      const reg = mkRegistry()
      reg.noteDevice({ instanceId: 'inst-1', name: 'Phone1', protocol: 'androidauto' })
      reg.noteDevice({ instanceId: 'inst-2', name: 'Phone2', protocol: 'androidauto' })

      const sessions = new SessionManager({ route: () => {} })
      const s1 = sessions.upsert(mkDriver(), 'androidauto', 'usb', { instanceId: 'inst-1' })
      sessions.upsert(mkDriver(), 'androidauto', 'usb', { instanceId: 'inst-2' })

      const ctrl = mkController(reg, sessions)
      // Close the first session — the second should now be ordinal 1
      sessions.close(s1.index)
      const views = ctrl.getDevices()
      const v2 = views.find((v) => v.name === 'Phone2')
      expect(v2?.session).toBe(1)
    })
  })

  // M2/M3: DeviceView carries `aliases` (the full id set, for stable phoneId
  // resolution) and `sessionIndex` (the stable session index, unlike `session`).
  describe('DeviceView carries aliases and sessionIndex (M2/M3)', () => {
    it('DeviceView has an aliases field exposing every known id', () => {
      const reg = mkRegistry()
      reg.noteDevice({
        usbSerial: 'SER001',
        instanceId: 'inst-1',
        name: 'Phone1',
        protocol: 'androidauto'
      })
      const sessions = new SessionManager({ route: () => {} })
      sessions.upsert(mkDriver(), 'androidauto', 'usb', { instanceId: 'inst-1' })
      const ctrl = mkController(reg, sessions)
      const views = ctrl.getDevices()
      expect(views[0]).toHaveProperty('aliases')
      // usbSerial is NOT in deviceId()'s priority chain (C1) but MUST be in aliases.
      expect(views[0].aliases?.usbSerial).toBe('SER001')
      expect(views[0].aliases?.instanceId).toBe('inst-1')
    })

    it('sessionIndex is the stable ProjectionSession.index, not the ordinal', () => {
      const reg = mkRegistry()
      reg.noteDevice({ instanceId: 'inst-1', name: 'Phone1', protocol: 'androidauto' })
      reg.noteDevice({ instanceId: 'inst-2', name: 'Phone2', protocol: 'androidauto' })
      const sessions = new SessionManager({ route: () => {} })
      const s1 = sessions.upsert(mkDriver(), 'androidauto', 'usb', { instanceId: 'inst-1' })
      const s2 = sessions.upsert(mkDriver(), 'androidauto', 'usb', { instanceId: 'inst-2' })
      // Close the first session: the ordinal `session` renumbers (C2), but
      // sessionIndex stays pinned to the underlying stable index.
      sessions.close(s1.index)
      const ctrl = mkController(reg, sessions)
      const v2 = ctrl.getDevices().find((v) => v.name === 'Phone2')
      expect(v2?.sessionIndex).toBe(s2.index)
      expect(v2?.session).toBe(1) // ordinal renumbered
    })
  })
})
