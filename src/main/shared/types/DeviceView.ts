/** A device tile in the unified picker: native registry entry or dongle device.
 *  The single cross-boundary shape — main builds it, the renderer only mirrors it. */
export interface DeviceView {
  id: string
  name?: string
  model?: string
  protocol?: 'carplay' | 'androidauto'
  lastTransport?: string
  status: 'active' | 'available' | 'offline'
  source?: 'native' | 'dongle'
  batteryLevel?: number
  batteryCharging?: boolean
  signalStrength?: number
  carrierName?: string
  session?: number
  // [hub] M2/M3: the full alias set for this device, so the hub layer can resolve
  // it to its own stable phoneId (C1). Distinct from `session` (an unstable ordinal).
  aliases?: {
    btMac?: string
    wifiMac?: string
    usbUdid?: string
    usbSerial?: string
    instanceId?: string
    ip?: string
  }
  // [hub] M2/M3: the stable ProjectionSession.index (never renumbers, unlike `session`).
  sessionIndex?: number
}
