// [hub] M11 — the hub palette. This is the ONE module allowed to contain colour
// literals; every hub component consumes these semantic tokens, so light/dark
// are switched in a single place and a designer can retune the whole shell here.
// Calm, domestic, low-stimulation by intent (DESIGN_VISION): the ambient surface
// must never be interesting enough to graze on.
import type { PresenceLevel } from './types'

export type HubMode = 'light' | 'dark'

export interface HubTokens {
  bg: string
  surface: string
  surfaceMuted: string
  border: string
  text: string
  textMuted: string
  ok: string
  warn: string
  danger: string
  ring: string
  presence: Record<PresenceLevel, string>
}

const dark: HubTokens = {
  bg: '#0E1116',
  surface: '#171B22',
  surfaceMuted: '#1F242D',
  border: '#2A303B',
  text: '#E6E9EF',
  textMuted: '#8B94A3',
  ok: '#5FB37A',
  warn: '#D4A24E',
  danger: '#D46A5D',
  ring: '#4F7CAC',
  presence: {
    absent: '#3A414D',
    nearby: '#5A6472',
    present: '#7C89C0',
    docked: '#5FB37A',
    projecting: '#4F9CD4'
  }
}

const light: HubTokens = {
  bg: '#F4F6F9',
  surface: '#FFFFFF',
  surfaceMuted: '#EAEEF3',
  border: '#D5DBE3',
  text: '#1B2028',
  textMuted: '#5A6472',
  ok: '#3E8E5A',
  warn: '#B07C2E',
  danger: '#B24A3E',
  ring: '#3C6690',
  presence: {
    absent: '#C2CAD4',
    nearby: '#9AA6B4',
    present: '#5A6AA8',
    docked: '#3E8E5A',
    projecting: '#2F7FB8'
  }
}

export function hubTokens(mode: HubMode): HubTokens {
  return mode === 'dark' ? dark : light
}
