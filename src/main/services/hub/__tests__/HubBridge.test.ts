/**
 * Integration test — HubBridge (Phase 1.1)
 *
 * Exercises the real net server over a real socket/pipe: control replies, the
 * event subscription stream, and recovery after the bridge is stopped and
 * restarted (the "kill either side and restart recovers" done-condition).
 */
import net from 'node:net'
import os from 'node:os'
import path from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import type { ProjectionEvent } from '../../projection/services/types'
import { HubBridge, type HubBridgeHost } from '../HubBridge'

function uniqueSocketPath(): string {
  const name = `hearth-hub-test-${process.pid}-${Math.random().toString(36).slice(2)}`
  return process.platform === 'win32'
    ? `\\\\.\\pipe\\${name}`
    : path.join(os.tmpdir(), `${name}.sock`)
}

/** Minimal line-delimited-JSON client. Resolves control replies by `id` and
 *  collects pushed `{ev}` frames. */
class TestClient {
  private sock: net.Socket
  private buf = ''
  private nextId = 1
  private readonly pending = new Map<number, (r: Record<string, unknown>) => void>()
  readonly events: Record<string, unknown>[] = []
  private onEvent: (() => void) | null = null

  private constructor(sock: net.Socket) {
    this.sock = sock
    sock.setEncoding('utf8')
    sock.on('data', (chunk: string) => {
      this.buf += chunk
      let nl = this.buf.indexOf('\n')
      while (nl >= 0) {
        const line = this.buf.slice(0, nl).trim()
        this.buf = this.buf.slice(nl + 1)
        if (line) this.dispatch(JSON.parse(line))
        nl = this.buf.indexOf('\n')
      }
    })
  }

  static connect(socketPath: string): Promise<TestClient> {
    return new Promise((resolve, reject) => {
      const sock = net.createConnection(socketPath)
      sock.once('error', reject)
      sock.once('connect', () => resolve(new TestClient(sock)))
    })
  }

  private dispatch(obj: Record<string, unknown>): void {
    if (typeof obj.id === 'number' && this.pending.has(obj.id)) {
      this.pending.get(obj.id)!(obj)
      this.pending.delete(obj.id)
      return
    }
    if (obj.ev !== undefined) {
      this.events.push(obj)
      this.onEvent?.()
    }
  }

  cmd(cmd: string, args?: Record<string, unknown>): Promise<Record<string, unknown>> {
    const id = this.nextId++
    return new Promise((resolve) => {
      this.pending.set(id, resolve)
      this.sock.write(`${JSON.stringify({ id, cmd, args })}\n`)
    })
  }

  waitForEvents(count: number, timeoutMs = 1000): Promise<Record<string, unknown>[]> {
    return new Promise((resolve, reject) => {
      const check = (): boolean => {
        if (this.events.length >= count) {
          resolve(this.events)
          return true
        }
        return false
      }
      if (check()) return
      const timer = setTimeout(() => reject(new Error('event timeout')), timeoutMs)
      this.onEvent = () => {
        if (check()) {
          clearTimeout(timer)
          this.onEvent = null
        }
      }
    })
  }

  close(): void {
    this.sock.destroy()
  }
}

type MkHost = {
  host: HubBridgeHost
  emit: (e: ProjectionEvent) => void
  saved: Record<string, unknown>[]
  pushedState: unknown[]
  restarted: () => number
}

function mkHost(): MkHost {
  const taps = new Set<(e: ProjectionEvent) => void>()
  const saved: Record<string, unknown>[] = []
  const pushedState: unknown[] = []
  let restarts = 0
  const host: HubBridgeHost = {
    getDevices: () => [{ id: 'aa:bb', name: 'Pixel', sessionIndex: 1 }],
    selectDevice: (id) => ({ ok: id === 'aa:bb' }),
    cycleSession: () => {},
    forgetDevice: () => ({ ok: true }),
    connectPairedDevice: async () => ({ ok: true }),
    getTransportState: () => ({ active: 'aa' }),
    switchTransport: async () => ({ ok: true, active: 'cp' }),
    getVersion: () => '8.0.0',
    getSettings: () => ({ darkMode: true }),
    saveSettings: (partial) => {
      saved.push(partial)
      return { ok: true }
    },
    restartApp: () => {
      restarts += 1
    },
    onPushState: (state) => {
      pushedState.push(state)
    },
    onEvent: (listener) => {
      taps.add(listener)
      return () => taps.delete(listener)
    }
  }
  return {
    host,
    emit: (e) => taps.forEach((t) => t(e)),
    saved,
    pushedState,
    restarted: () => restarts
  }
}

describe('HubBridge', () => {
  let bridge: HubBridge
  let socketPath: string

  afterEach(async () => {
    await bridge?.stop()
  })

  it('answers a control command with a reply keyed by id', async () => {
    socketPath = uniqueSocketPath()
    bridge = new HubBridge(mkHost().host, socketPath)
    bridge.start()
    const client = await TestClient.connect(socketPath)
    const reply = await client.cmd('getDevices')
    expect(reply.ok).toBe(true)
    expect(reply.result).toEqual([{ id: 'aa:bb', name: 'Pixel', sessionIndex: 1 }])
    client.close()
  })

  it('rejects an unknown command without throwing', async () => {
    socketPath = uniqueSocketPath()
    bridge = new HubBridge(mkHost().host, socketPath)
    bridge.start()
    const client = await TestClient.connect(socketPath)
    const reply = await client.cmd('doNotExist')
    expect(reply.ok).toBe(false)
    expect(String(reply.error)).toContain('unknown-cmd')
    client.close()
  })

  it('streams projection events to a subscribed connection', async () => {
    socketPath = uniqueSocketPath()
    const { host, emit } = mkHost()
    bridge = new HubBridge(host, socketPath)
    bridge.start()
    const client = await TestClient.connect(socketPath)
    const sub = await client.cmd('subscribe')
    expect(sub.subscribed).toBe(true)

    emit({ type: 'plugged', phoneType: 1 as never })
    emit({
      type: 'callState',
      payload: { phase: 'incoming', sessionIndex: 1, at: '2026-01-01T00:00:00Z' }
    })
    const events = await client.waitForEvents(2)
    const kinds = events.map((e) => e.ev)
    expect(kinds).toContain('plugged')
    expect(kinds).toContain('callState')
    const callFrame = events.find((e) => e.ev === 'callState')!
    expect((callFrame.payload as { phase: string }).phase).toBe('incoming')
    client.close()
  })

  it('does not deliver events to a connection that never subscribed', async () => {
    socketPath = uniqueSocketPath()
    const { host, emit } = mkHost()
    bridge = new HubBridge(host, socketPath)
    bridge.start()
    const client = await TestClient.connect(socketPath)
    emit({ type: 'unplugged' })
    await new Promise((r) => setTimeout(r, 50))
    expect(client.events).toHaveLength(0)
    client.close()
  })

  it('marshals settings, restart and pushState commands to the host', async () => {
    socketPath = uniqueSocketPath()
    const h = mkHost()
    bridge = new HubBridge(h.host, socketPath)
    bridge.start()
    const client = await TestClient.connect(socketPath)

    const got = await client.cmd('getSettings')
    expect(got.result).toEqual({ darkMode: true })

    const saved = await client.cmd('saveSettings', { settings: { darkMode: false } })
    expect(saved.ok).toBe(true)
    expect(h.saved).toEqual([{ darkMode: false }])

    const pushed = await client.cmd('pushState', { state: { rev: 3 } })
    expect(pushed.ok).toBe(true)
    expect(h.pushedState).toEqual([{ rev: 3 }])

    const restarted = await client.cmd('restartApp')
    expect(restarted.ok).toBe(true)
    expect(h.restarted()).toBe(1)
    client.close()
  })

  it('broadcastIntent reaches a subscribed connection as an {ev:intent} frame', async () => {
    socketPath = uniqueSocketPath()
    bridge = new HubBridge(mkHost().host, socketPath)
    bridge.start()
    const client = await TestClient.connect(socketPath)
    await client.cmd('subscribe')
    bridge.broadcastIntent({ type: 'phone.rename', phoneId: 'P', name: 'Kitchen' })
    const events = await client.waitForEvents(1)
    expect(events[0].ev).toBe('intent')
    expect((events[0].payload as { type: string }).type).toBe('phone.rename')
    client.close()
  })

  it('recovers after the bridge is stopped and restarted (resync)', async () => {
    socketPath = uniqueSocketPath()
    const { host } = mkHost()
    bridge = new HubBridge(host, socketPath)
    bridge.start()
    const first = await TestClient.connect(socketPath)
    expect((await first.cmd('getDevices')).ok).toBe(true)
    first.close()

    await bridge.stop()

    // hubd would reconnect with backoff and re-run getDevices — simulate that.
    bridge = new HubBridge(host, socketPath)
    bridge.start()
    const second = await TestClient.connect(socketPath)
    const reply = await second.cmd('getDevices')
    expect(reply.ok).toBe(true)
    second.close()
  })
})
