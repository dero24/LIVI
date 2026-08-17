// [hub] Stage 1.1 — the hub's ringtone.
//
// DESIGN_VISION: "The ringtone is gentle but present, audible from the next room.
// Not a panic sound. A summons." So this is NOT a beep — it is a warm two-strike
// bell motif that repeats on a ~3 s "breathing" cadence, synthesised in-process
// and played through LIVI's configured `audioOutputDevice`. It reuses the same
// AudioOutput/GStreamer path as SystemSound, so there is no new dependency and
// the hub speaker is the one that rings (the docked phone may be muted/charging).
//
// hubd drives this over the HubBridge: `playRingtone` when HubState.ring.tone
// goes true (all policy/DND/quiet-hours/active-call gating already applied in
// hubd/ring.py), `stopRingtone` when it goes false (answer/decline/silence/end).
import { AudioOutput } from './AudioOutput'

type RingtoneConfig = {
  audioOutputDevice?: string
  disableAudioOutput?: boolean
  systemSoundsVolume?: number
}

const SR = 48000
const CHANNELS = 2
const GEN_INTERVAL_MS = 30
const MAX_CATCHUP_FRAMES = SR >> 2 // 250 ms — cap catch-up after a timer stall
const DEFAULT_VOLUME = 0.8 // a ring should carry to the next room

/** Mirror of SystemSound's perceptual volume curve (-60 dB … 0 dB). */
function gainFromVolume(volume: number): number {
  const v = Math.max(0, Math.min(1, Number.isFinite(volume) ? volume : 0))
  if (v <= 0) return 0
  return 10 ** ((-60 + 60 * v) / 20)
}

/**
 * Pre-render one ~3 s pattern: two warm bell strikes ("ding — dong", a rising
 * perfect fourth) followed by a rest, so the tone breathes rather than nagging.
 * Each strike is a soft-attack bell (fundamental + two gently inharmonic
 * partials) with a ~0.5 s decay.
 */
function renderRingtonePattern(): Float32Array {
  const PATTERN_S = 3.0
  const len = Math.floor(SR * PATTERN_S)
  const out = new Float32Array(len)

  const strikes = [
    { atS: 0.0, freq: 587.33 }, // D5
    { atS: 0.5, freq: 783.99 } // G5 — a warm, inviting rise
  ]
  // [partial multiple, amplitude] — slightly inharmonic upper partials read as a
  // struck bell/chime rather than a synth beep.
  const partials: Array<[number, number]> = [
    [1, 1.0],
    [2.01, 0.35],
    [3.02, 0.16]
  ]

  for (const s of strikes) {
    const start = Math.floor(s.atS * SR)
    const dur = Math.floor(1.7 * SR)
    for (let i = 0; i < dur && start + i < len; i++) {
      const t = i / SR
      // Soft attack (~8 ms) so sample 0 is not a click; ~0.5 s exponential decay.
      const env = Math.exp(-t / 0.5) * (1 - Math.exp(-t / 0.008))
      let v = 0
      for (const [mult, amp] of partials) v += amp * Math.sin(2 * Math.PI * s.freq * mult * t)
      out[start + i] += 0.5 * env * v
    }
  }

  // Peak-normalise so volume is predictable regardless of partial summing.
  let peak = 0
  for (let i = 0; i < len; i++) peak = Math.max(peak, Math.abs(out[i]))
  if (peak > 0) {
    const norm = 0.9 / peak
    for (let i = 0; i < len; i++) out[i] *= norm
  }
  return out
}

/** The hub ringtone: an independent looping audio channel, on/off from hubd. */
export class Ringtone {
  private out: AudioOutput | null = null
  private timer: ReturnType<typeof setInterval> | null = null
  private active = false
  private streamStartMs = 0
  private framesProduced = 0
  private readonly pattern = renderRingtonePattern()

  constructor(private readonly getConfig: () => RingtoneConfig) {}

  /** Start ringing (idempotent). Respects the global audio-output mute. */
  start(): void {
    if (this.active) return
    if (this.getConfig().disableAudioOutput) return
    this.active = true
    this.ensureRunning()
  }

  /** Stop ringing (idempotent). */
  stop(): void {
    if (!this.active && !this.out) return
    this.active = false
    if (this.timer) {
      clearInterval(this.timer)
      this.timer = null
    }
    if (this.out) {
      try {
        this.out.stop()
      } catch {
        // ignore
      }
      this.out = null
    }
  }

  /** Audio output device changed in config: re-open on the new device if ringing. */
  onDeviceChanged(): void {
    if (!this.active) return
    this.stop()
    this.start()
  }

  dispose(): void {
    this.stop()
  }

  private ensureRunning(): void {
    if (this.out) return
    const cfg = this.getConfig()
    this.out = new AudioOutput({
      sampleRate: SR,
      channels: CHANNELS,
      mode: 'realtime',
      device: cfg.audioOutputDevice || undefined
    })
    this.out.start()
    this.streamStartMs = Date.now()
    this.framesProduced = 0
    this.timer = setInterval(() => this.generate(), GEN_INTERVAL_MS)
    this.timer.unref?.()
  }

  /** Produce exactly the frames that should have played by now (wall-clock paced),
   *  looping the pre-rendered pattern. */
  private generate(): void {
    const out = this.out
    if (!out) return

    const now = Date.now()
    const targetFrames = Math.floor(((now - this.streamStartMs) / 1000) * SR)
    let n = targetFrames - this.framesProduced
    if (n <= 0) return
    if (n > MAX_CATCHUP_FRAMES) {
      this.framesProduced = targetFrames - MAX_CATCHUP_FRAMES
      n = MAX_CATCHUP_FRAMES
    }

    const gain = gainFromVolume(this.getConfig().systemSoundsVolume ?? DEFAULT_VOLUME)
    const patLen = this.pattern.length
    const pcm = new Int16Array(n * CHANNELS)

    for (let i = 0; i < n; i++) {
      const frame = this.framesProduced + i
      const s = this.pattern[frame % patLen] ?? 0
      let v = s * gain * 32767
      if (v > 32767) v = 32767
      else if (v < -32768) v = -32768
      const iv = v | 0
      pcm[i * 2] = iv
      pcm[i * 2 + 1] = iv
    }

    this.framesProduced += n
    out.write(pcm)
  }
}
