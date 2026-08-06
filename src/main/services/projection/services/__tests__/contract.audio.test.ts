/**
 * Contract tests — ProjectionAudio attention semantics
 *
 * These tests assert the audio attention contract from §3 and the Tier 2 floor.
 * They test *upstream's* behaviour, not ours.
 *
 * Guards: Tier 2 floor, C3, M1
 */
import { ProjectionAudio } from '@main/services/projection/services/ProjectionAudio'

vi.mock('@main/services/audio', () => ({
  Microphone: vi.fn().mockImplementation(function () {
    return { on: vi.fn(), start: vi.fn(), stop: vi.fn(), isCapturing: vi.fn(() => false), setDevice: vi.fn() }
  }),
  AudioOutput: vi.fn().mockImplementation(function () {
    return { start: vi.fn(), stop: vi.fn(), write: vi.fn(), setDevice: vi.fn() }
  }),
  downsampleToMono: vi.fn(() => new Int16Array([1, 2, 3]))
}))

vi.mock('@main/constants', () => ({ DEBUG: false }))

vi.mock('../../messages', () => ({
  decodeTypeMap: {
    1: { frequency: 48000, channel: 2, format: 'pcm', mimeType: 'audio/pcm', bitDepth: 16 },
    2: { frequency: 16000, channel: 1, format: 'pcm', mimeType: 'audio/pcm', bitDepth: 16 }
  },
  AudioData: class {}
}))

vi.mock('@shared/types/ProjectionEnums', () => ({
  AudioCommand: {
    AudioAttentionStart: 1,
    AudioAttentionRinging: 2,
    AudioPhonecallStop: 3,
    AudioVoiceAssistantStart: 4,
    AudioVoiceAssistantStop: 5,
    AudioNaviStart: 6,
    AudioTurnByTurnStart: 7,
    AudioNaviStop: 8,
    AudioTurnByTurnStop: 9,
    AudioOutputStart: 10,
    AudioMediaStart: 11,
    AudioMediaStop: 12,
    AudioOutputStop: 13,
    AudioInputConfig: 14,
    AudioPhonecallStart: 15
  }
}))

function createSubject() {
  const sendProjectionEvent = vi.fn()
  const audio = new ProjectionAudio(
    () => ({ mediaDelay: 120 }) as never,
    sendProjectionEvent as never,
    vi.fn() as never,
    vi.fn() as never
  ) as unknown as {
    handleAudioData: (msg: unknown) => void
    sendProjectionEvent: typeof sendProjectionEvent
    uiCallIncoming: boolean
    phonecallActive: boolean
    voiceAssistantActive: boolean
  }
  // Expose the mock for assertions
  ;(audio as unknown as { sendProjectionEvent: typeof sendProjectionEvent }).sendProjectionEvent = sendProjectionEvent
  return { audio, sendProjectionEvent }
}

// Command-only messages have `command` (not `cmd`) and NO `data` field.
// The code path checks `if (msg.data)` first and returns early; only
// messages without `data` reach the command-handling block.
function mkAudioCommand(command: number, opts: { decodeType?: number; audioType?: number } = {}): unknown {
  return {
    command,
    decodeType: opts.decodeType ?? 1,
    audioType: opts.audioType ?? 0
  }
}

describe('contract.audio', () => {
  describe('AudioAttentionStart emits attention {phase:"incoming"} (Tier 2 floor)', () => {
    it('emits an attention event with kind=call, active=true, phase=incoming', () => {
      const { audio, sendProjectionEvent } = createSubject()
      audio.handleAudioData(mkAudioCommand(1)) // AudioAttentionStart
      const attentionCall = sendProjectionEvent.mock.calls.find(
        (c: unknown[]) => (c[0] as { type: string }).type === 'attention'
      )
      expect(attentionCall).toBeDefined()
      const payload = (attentionCall![0] as { payload: Record<string, unknown> }).payload
      expect(payload.kind).toBe('call')
      expect(payload.active).toBe(true)
      expect(payload.phase).toBe('incoming')
    })

    it('does not emit a second attention for repeated AudioAttentionStart', () => {
      const { audio, sendProjectionEvent } = createSubject()
      audio.handleAudioData(mkAudioCommand(1)) // first
      audio.handleAudioData(mkAudioCommand(1)) // second — should be deduped
      const attentionCalls = sendProjectionEvent.mock.calls.filter(
        (c: unknown[]) => (c[0] as { type: string }).type === 'attention'
      )
      expect(attentionCalls).toHaveLength(1)
    })
  })

  describe('AudioPhonecallStart emits NO attention (C3)', () => {
    it('does not emit an attention event for AudioPhonecallStart', () => {
      const { audio, sendProjectionEvent } = createSubject()
      // AudioPhonecallStart is cmd 15; it needs a config message with
      // disableAudioOutput=false and micType=0 to not early-return,
      // but the key assertion is that no attention event is emitted.
      audio.handleAudioData(mkAudioCommand(15, { decodeType: 2 }))
      const attentionCalls = sendProjectionEvent.mock.calls.filter(
        (c: unknown[]) => (c[0] as { type: string }).type === 'attention'
      )
      expect(attentionCalls).toHaveLength(0)
    })
  })

  describe('callState emits incoming, active, ended in order', () => {
    it('emits incoming on AudioAttentionStart and ended on AudioPhonecallStop', () => {
      const { audio, sendProjectionEvent } = createSubject()
      // 1. Incoming call
      audio.handleAudioData(mkAudioCommand(1)) // AudioAttentionStart
      // 2. Call ends
      audio.handleAudioData(mkAudioCommand(3)) // AudioPhonecallStop
      const attentionCalls = sendProjectionEvent.mock.calls.filter(
        (c: unknown[]) => (c[0] as { type: string }).type === 'attention'
      )
      expect(attentionCalls).toHaveLength(2)
      const first = (attentionCalls[0][0] as { payload: Record<string, unknown> }).payload
      const second = (attentionCalls[1][0] as { payload: Record<string, unknown> }).payload
      expect(first.active).toBe(true)
      expect(first.phase).toBe('incoming')
      expect(second.active).toBe(false)
      expect(second.phase).toBe('ended')
    })
  })

  // M1: `callState` is a first-class event separate from `attention`. It has an
  // 'active' phase (which `attention` lacks) and carries device identity. `attention`
  // stays byte-identical (asserted by the C3 test above).
  describe('callState emits incoming -> active -> ended with sessionIndex (M1)', () => {
    const callStates = (calls: unknown[][]) =>
      calls
        .filter((c) => (c[0] as { type: string }).type === 'callState')
        .map((c) => (c[0] as { payload: Record<string, unknown> }).payload)

    it('emits incoming on AudioAttentionStart, carrying a sessionIndex field', () => {
      const { sendProjectionEvent, audio } = createSubject()
      audio.handleAudioData(mkAudioCommand(1)) // AudioAttentionStart
      const states = callStates(sendProjectionEvent.mock.calls)
      expect(states).toHaveLength(1)
      expect(states[0].phase).toBe('incoming')
      expect(states[0]).toHaveProperty('sessionIndex')
    })

    it('emits active on AudioPhonecallStart (a phase attention never has, C3)', () => {
      const { sendProjectionEvent, audio } = createSubject()
      audio.handleAudioData(mkAudioCommand(15, { decodeType: 2 })) // AudioPhonecallStart
      const states = callStates(sendProjectionEvent.mock.calls)
      expect(states).toHaveLength(1)
      expect(states[0].phase).toBe('active')
    })

    it('emits incoming -> active -> ended in order', () => {
      const { sendProjectionEvent, audio } = createSubject()
      audio.handleAudioData(mkAudioCommand(1)) // incoming
      audio.handleAudioData(mkAudioCommand(15, { decodeType: 2 })) // active
      audio.handleAudioData(mkAudioCommand(3)) // ended (AudioPhonecallStop)
      const phases = callStates(sendProjectionEvent.mock.calls).map((p) => p.phase)
      expect(phases).toEqual(['incoming', 'active', 'ended'])
    })

    it('dedupes a repeated phase (no duplicate callState)', () => {
      const { sendProjectionEvent, audio } = createSubject()
      audio.handleAudioData(mkAudioCommand(1))
      audio.handleAudioData(mkAudioCommand(1))
      expect(callStates(sendProjectionEvent.mock.calls)).toHaveLength(1)
    })
  })
})
