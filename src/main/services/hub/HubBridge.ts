// [hub] Phase 1.1 — the HubBridge.
//
// A Unix-domain socket served by LIVI's MAIN process, in LIVI's own
// line-delimited-JSON idiom (the same shape as the AA/CP BT helper sockets).
// It is the single channel between the projection plane (this process) and the
// reachability plane (`hubd`, a separate Python daemon). It replaces R3's
// `actions[]` queue, `POST /livi-event` overlay and the Socket.IO telemetry
// client all at once.
//
// Design rules (§7.3):
//   - The bridge contains NO policy. It marshals: commands in, events out.
//   - Every control request carries an `id` and gets exactly one reply.
//   - `hubd` may open one connection for control and one for events (or reuse a
//     single connection for both — `subscribe` promotes a connection to also
//     receive the event stream).
//   - LIVI works with no `hubd` attached; the bridge is never a single point of
//     failure for projection.
import fs from 'node:fs'
import net from 'node:net'
import os from 'node:os'
import path from 'node:path'
import type { ProjectionEvent } from '../projection/services/types'

/** The control surface the bridge is allowed to marshal. Deliberately narrow —
 *  it is an audited allow-list, not "all of ProjectionService". */
export interface HubBridgeHost {
  getDevices(): unknown
  selectDevice(id: string): { ok: boolean }
  cycleSession(): void
  forgetDevice(id: string): { ok: boolean }
  connectPairedDevice(mac: string): Promise<{ ok: boolean; error?: string }>
  getTransportState(): unknown
  switchTransport(): Promise<{ ok: boolean; active: unknown }>
  getVersion?(): string | null
  getSettings(): unknown
  saveSettings(partial: Record<string, unknown>): { ok: boolean }
  restartApp(): void
  /** hubd pushes assembled HubState here; main forwards it to renderers. */
  onPushState(state: unknown): void
  /** Register a tap on the projection event stream. Returns an unsubscribe fn. */
  onEvent(listener: (e: ProjectionEvent) => void): () => void
}

type Reply = Record<string, unknown>

/** `$XDG_RUNTIME_DIR/hearth/hub.sock`, falling back to a temp dir. On Windows
 *  (dev/CI) we use a named pipe so the bridge and its tests still run. */
export function defaultHubSocketPath(): string {
  if (process.platform === 'win32') return '\\\\.\\pipe\\hearth-hub'
  const runtime = process.env.XDG_RUNTIME_DIR || path.join(os.tmpdir(), 'hearth-runtime')
  return path.join(runtime, 'hearth', 'hub.sock')
}

const isPipe = (p: string): boolean => p.startsWith('\\\\')

export class HubBridge {
  private server: net.Server | null = null
  private readonly clients = new Set<net.Socket>()
  private readonly subscribers = new Set<net.Socket>()
  private unsubEvents: (() => void) | null = null

  constructor(
    private readonly host: HubBridgeHost,
    private readonly socketPath: string = defaultHubSocketPath()
  ) {}

  start(): void {
    this.prepareSocketPath()
    this.server = net.createServer((sock) => this.onConnection(sock))
    this.server.on('error', (e) => console.error('[HubBridge] server error:', (e as Error).message))
    this.server.listen(this.socketPath, () => {
      if (!isPipe(this.socketPath)) {
        try {
          fs.chmodSync(this.socketPath, 0o600)
        } catch {}
      }
      console.log(`[HubBridge] listening on ${this.socketPath}`)
    })
    this.unsubEvents = this.host.onEvent((e) => this.broadcastEvent(e))
  }

  private prepareSocketPath(): void {
    if (isPipe(this.socketPath)) return
    try {
      fs.mkdirSync(path.dirname(this.socketPath), { recursive: true, mode: 0o700 })
    } catch {}
    // Remove a stale socket left by a previous crash so listen() does not EADDRINUSE.
    try {
      fs.rmSync(this.socketPath, { force: true })
    } catch {}
  }

  private onConnection(sock: net.Socket): void {
    this.clients.add(sock)
    sock.setEncoding('utf8')
    let buf = ''
    sock.on('data', (chunk: string) => {
      buf += chunk
      let nl = buf.indexOf('\n')
      while (nl >= 0) {
        const line = buf.slice(0, nl).trim()
        buf = buf.slice(nl + 1)
        if (line) void this.handleLine(sock, line)
        nl = buf.indexOf('\n')
      }
    })
    sock.on('error', () => {})
    sock.on('close', () => {
      this.clients.delete(sock)
      this.subscribers.delete(sock)
    })
  }

  private send(sock: net.Socket, obj: Reply): void {
    try {
      sock.write(`${JSON.stringify(obj)}\n`)
    } catch {}
  }

  private broadcastEvent(e: ProjectionEvent): void {
    if (this.subscribers.size === 0) return
    const frame = `${JSON.stringify({ ev: e.type, ...e })}\n`
    for (const s of this.subscribers) {
      try {
        s.write(frame)
      } catch {}
    }
  }

  /** Forward a renderer intent to hubd as an `{ev:'intent'}` frame. This is the
   *  renderer -> main -> bridge -> hubd path (M7). Safe no-op if hubd is absent. */
  broadcastIntent(payload: unknown): void {
    if (this.subscribers.size === 0) return
    const frame = `${JSON.stringify({ ev: 'intent', payload })}\n`
    for (const s of this.subscribers) {
      try {
        s.write(frame)
      } catch {}
    }
  }

  private async handleLine(sock: net.Socket, line: string): Promise<void> {
    let msg: { id?: unknown; cmd?: string; args?: Record<string, unknown> }
    try {
      msg = JSON.parse(line)
    } catch {
      return this.send(sock, { ok: false, error: 'bad-json' })
    }
    const id = msg.id
    const reply = (extra: Reply): void =>
      this.send(sock, { ...(id != null ? { id } : {}), ...extra })
    const args = msg.args ?? {}
    try {
      switch (msg.cmd) {
        case 'subscribe':
          this.subscribers.add(sock)
          return reply({ ok: true, subscribed: true })
        case 'getDevices':
          return reply({ ok: true, result: this.host.getDevices() })
        case 'selectDevice':
          return reply({ ...this.host.selectDevice(String(args.id ?? '')) })
        case 'cycleSession':
          this.host.cycleSession()
          return reply({ ok: true })
        case 'forgetDevice':
          return reply({ ...this.host.forgetDevice(String(args.id ?? '')) })
        case 'connectPairedDevice':
          return reply({ ...(await this.host.connectPairedDevice(String(args.mac ?? ''))) })
        case 'getTransportState':
          return reply({ ok: true, result: this.host.getTransportState() })
        case 'switchTransport':
          return reply({ ...(await this.host.switchTransport()) })
        case 'getVersion':
          return reply({ ok: true, result: this.host.getVersion?.() ?? null })
        case 'getSettings':
          return reply({ ok: true, result: this.host.getSettings() })
        case 'saveSettings':
          return reply({
            ...this.host.saveSettings((args.settings as Record<string, unknown>) ?? {})
          })
        case 'restartApp':
          this.host.restartApp()
          return reply({ ok: true })
        case 'pushState':
          this.host.onPushState(args.state)
          return reply({ ok: true })
        case 'ping':
          return reply({ ok: true, pong: true })
        default:
          return reply({ ok: false, error: `unknown-cmd:${String(msg.cmd)}` })
      }
    } catch (err) {
      return reply({ ok: false, error: (err as Error).message })
    }
  }

  async stop(): Promise<void> {
    this.unsubEvents?.()
    this.unsubEvents = null
    for (const s of this.clients) {
      try {
        s.destroy()
      } catch {}
    }
    this.clients.clear()
    this.subscribers.clear()
    await new Promise<void>((resolve) => {
      if (!this.server) return resolve()
      this.server.close(() => resolve())
      this.server = null
    })
    if (!isPipe(this.socketPath)) {
      try {
        fs.rmSync(this.socketPath, { force: true })
      } catch {}
    }
  }
}
