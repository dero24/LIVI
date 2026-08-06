// [hub] M7 — the renderer<->hub IPC bridge.
//
// Two channels:
//   - `hub:intent`  renderer -> main -> HubBridge -> hubd  (the mutation path)
//   - `hub:state`   hubd -> HubBridge -> main -> renderer   (push, emit-on-change)
//     plus `hub:getState` so a freshly-loaded renderer can pull the last state
//     without waiting for the next push.
import type { HubBridge } from '@main/services/hub/HubBridge'
import { BrowserWindow, ipcMain } from 'electron'

let lastHubState: unknown = null

export function registerHubIpc(hubBridge: HubBridge): void {
  ipcMain.removeHandler('hub:intent')
  ipcMain.removeHandler('hub:getState')
  ipcMain.handle('hub:intent', (_event, payload: unknown) => {
    hubBridge.broadcastIntent(payload)
    return { ok: true }
  })
  ipcMain.handle('hub:getState', () => lastHubState)
}

// Called from the HubBridge `onPushState` host hook when hubd publishes state.
export function broadcastHubState(state: unknown): void {
  lastHubState = state
  for (const win of BrowserWindow.getAllWindows()) {
    if (!win.isDestroyed()) win.webContents.send('hub:state', state)
  }
}
