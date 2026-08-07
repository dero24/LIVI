// [hub] Renderer-side mirror of the HubState shape assembled by hubd, and the
// `window.hub` bridge exposed by the preload (M8). The renderer decides nothing
// (D7): it only draws what hubd sends and posts intents back.

export type PresenceLevel = 'absent' | 'nearby' | 'present' | 'docked' | 'projecting'

export interface HubPerson {
  name?: string
  colour?: string
  isPrimary?: boolean
  avatar?: string
}

export interface HubLiviData {
  batteryLevel?: number | null
  batteryCharging?: boolean | null
  signalStrength?: number | null
  carrierName?: string | null
  sessionIndex?: number | null
  status?: string
}

export interface HubPhone {
  phoneId: string
  person: HubPerson
  platform: 'android' | 'ios' | 'unknown'
  protocol: 'androidauto' | 'carplay' | null
  presence: { level: PresenceLevel; rank: number }
  companion?: unknown
  policy?: Record<string, unknown>
  livi?: HubLiviData | null
}

export interface HubDock {
  slotId: string
  label: string
  boundPhoneId: string | null
  sensor?: Record<string, unknown>
}

// [hub] Phase 2.3 — the ring block of HubState (§7.4, §12.6 state E). hubd
// resolves answerVia/canAnswerOnHub/canBringToHub; the renderer only draws.
export interface HubRingCaller {
  name: string | null
  number: string | null
  photo: string | null
}

export interface HubRingQueued {
  phoneId: string
  person: string | null
  caller: HubRingCaller
  state: string
  tier: number
}

export interface HubRing {
  phoneId: string
  person: string | null
  caller: HubRingCaller
  state: 'incoming' | 'active' | 'ended'
  tier: number
  tone: boolean
  startedAt: number
  canAnswerOnHub: boolean
  answerVia: 'projection' | 'hfp' | 'companion' | null
  canBringToHub: boolean
  queued: HubRingQueued[]
}

export interface HubState {
  v: number
  rev: number
  at?: string
  phones: HubPhone[]
  docks: HubDock[]
  ring?: HubRing | null
  transport?: unknown
  health?: { ok?: boolean; bridge?: boolean }
}

export interface HubIntentResult {
  ok: boolean
  [key: string]: unknown
}

export interface HubApi {
  onState(cb: (state: HubState) => void): () => void
  getState(): Promise<HubState | null>
  intent(payload: Record<string, unknown>): Promise<HubIntentResult>
}

declare global {
  interface Window {
    hub?: HubApi
  }
}
