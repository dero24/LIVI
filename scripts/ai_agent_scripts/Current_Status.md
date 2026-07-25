Short answer: **Use LIVI’s own dashboard (`Home.tsx`) for the dock-slot tabs and session switching, keep Android Auto for the active phone’s UI/calls, and add a tiny per-phone sidecar (Tasker first, then a small Android app) to make the hub ring when a non-active phone receives a call.** Android Auto alone cannot do multi-phone ring detection.

## What the READMEs and code say

I re-read `README.md` and the LIVI source. The LIVI README lists **“multi-session with live switching between connected phones”** as a feature, and the code backs that up partially:

- LIVI already has a session model with one **active** session and any number of **held** sessions, plus `activate(index)` and `cycleSession`. <ref_snippet file="C:\Users\Robby\Windsurf Projects\random_stuff\raspberry-pi_homephone\LIVI\src\main\services\projection\services\SessionManager.ts" lines="27-37" /> <ref_snippet file="C:\Users\Robby\Windsurf Projects\random_stuff\raspberry-pi_homephone\LIVI\src\main\services\projection\services\SessionManager.ts" lines="185-207" />
- LIVI already has a `Home` dashboard with device cards, `useDevices`, and `selectDevice(id)`. <ref_snippet file="C:\Users\Robby\Windsurf Projects\random_stuff\raspberry-pi_homephone\LIVI\src\renderer\src\components\pages\home\Home.tsx" lines="131-144" /> <ref_snippet file="C:\Users\Robby\Windsurf Projects\random_stuff\raspberry-pi_homephone\LIVI\src\renderer\src\components\pages\home\Home.tsx" lines="288-357" />
- `DeviceController.selectDevice` activates the matching session. <ref_snippet file="C:\Users\Robby\Windsurf Projects\random_stuff\raspberry-pi_homephone\LIVI\src\main\services\projection\services\DeviceController.ts" lines="55-78" />

## The blockers

1. **Only one wired phone is expected at a time.** `USBService` keeps a single `lastPhoneState` and `connectedPhoneDevice`, and a second phone attach is treated as a stale-state reset. <ref_snippet file="C:\Users\Robby\Windsurf Projects\random_stuff\raspberry-pi_homephone\LIVI\src\main\services\usb\USBService.ts" lines="33-35" /> <ref_snippet file="C:\Users\Robby\Windsurf Projects\random_stuff\raspberry-pi_homephone\LIVI\src\main\services\usb\USBService.ts" lines="159-174" /> `TransportArbiter` is also built around one phone. <ref_snippet file="C:\Users\Robby\Windsurf Projects\random_stuff\raspberry-pi_homephone\LIVI\src\main\services\projection\transport\TransportArbiter.ts" lines="80-107" />
2. **Only one Android Auto session is decoded/routed at a time.** `ProjectionDriverManager` has one `routed` driver and only the routed driver’s video/audio events reach the renderer. <ref_snippet file="C:\Users\Robby\Windsurf Projects\random_stuff\raspberry-pi_homephone\LIVI\src\main\services\projection\drivers\ProjectionDriverManager.ts" lines="59-87" /> `AAStack` also keeps a single `_activeSession`. <ref_snippet file="C:\Users\Robby\Windsurf Projects\random_stuff\raspberry-pi_homephone\LIVI\src\main\services\projection\driver\aa\stack\index.ts" lines="64-82" />
3. **Android Auto does not expose “incoming call” state to a held session.** There is no phone-status channel in the AA stack, and `AaEventBridge` only forwards media, nav, voice-assistant, and video-focus events. <ref_snippet file="C:\Users\Robby\Windsurf Projects\random_stuff\raspberry-pi_homephone\LIVI\src\main\services\projection\driver\aa\AaEventBridge.ts" lines="236-239" /> Calls only appear when the session is active and the phone paints its call UI.

So: **tabs/switching can live inside LIVI**, but **ringing for a non-active phone must come from outside Android Auto**.

## Proposed multi-device architecture

### 1. Tabs / dock slots — use LIVI’s own dashboard
- Map each physical dock slot to a USB port/hub location. The phone in Slot 1 is “Robby”, Slot 2 is “Partner”, etc.
- Customize `LIVI/src/renderer/src/components/pages/home/Home.tsx` to render Slot 1–Slot 4 cards. Each card shows:
  - Name, protocol icon (Android / iPhone), connection type (USB/Wi-Fi)
  - Battery, signal, charging status
  - `Active` / `Available` / `Offline` / `Ringing` badge
  - Tap a card to call `selectDevice(id)` and switch the active session.
- The existing `useDevices()` + `DeviceController` already give you the data and switching API, so the tab UI is the cheapest piece.

### 2. Switching behavior
- One active session drives the projection (video + audio).
- Tapping a slot calls `selectDevice(id)` → `SessionManager.activate(index)` → `ProjectionDriverManager.route(driver)`. <ref_snippet file="C:\Users\Robby\Windsurf Projects\random_stuff\raspberry-pi_homephone\LIVI\src\main\services\projection\services\SessionManager.ts" lines="185-197" /> <ref_snippet file="C:\Users\Robby\Windsurf Projects\random_stuff\raspberry-pi_homephone\LIVI\src\main\services\projection\drivers\ProjectionDriverManager.ts" lines="82-87" />
- Held sessions exist in `SessionManager` but are not routed, so they do not consume video/audio. Switching takes 1–2 seconds as the new session’s video plane comes up.

### 3. Ring / notification for non-active phones — add a sidecar
Android Auto will not tell you a held phone is ringing. Options, ranked by effort:

| Option | Effort | Pros | Cons |
|---|---|---|---|
| **A. Tasker / Automate profile** on each phone | Days | No app store, fast to prove, handles calls + selected notifications | Per-phone setup, relies on user installing Tasker |
| **B. Tiny Android companion app** | Weeks | Polished, caller ID, reliable, can use `NotificationListenerService` | Must build, sign, install on every phone |
| **C. Bluetooth HFP headset role for Pi** | Weeks | No phone app | Only one HFP link at a time, conflicts with wireless AA BT |
| **D. USB audio/switch hardware** | Weeks | Cleanest physically | One phone active at a time, slow switch, no ring detection |

**Recommendation:** Start with **A (Tasker)**. On each phone:
- Trigger: incoming call → HTTP POST to `http://homephone.local:8123/ring?slot=1&caller=...`
- Trigger: SMS/WhatsApp notification → same endpoint with `type=notify`
- Pi runs a small Python/Node listener that:
  - Plays a ringtone through the speaker
  - Sets the slot card to `Ringing` / shows a banner
  - On user tap, switches to that session, then sends the `acceptPhone` command
  - If no tap within N seconds, stops ringing

Once the flow is proven, replace Tasker with **B (companion app)** for a cleaner family experience.

### 4. Making two+ wired phones coexist (the LIVI changes)
To have Slot 1 and Slot 2 both plugged in and switchable without unplugging:

- `USBService` must track a `Map<slot, Device>` instead of one `connectedPhoneDevice`, and call `markPhoneConnected(true, device)` per slot.
- `TransportArbiter` must support multiple wired candidates, not just one `phoneConnected`/`phoneDevice`. `detectedCandidates()` should include every docked phone.
- `AaManager.bringUpWired()` already keys bridges by device serial, so it can support multiple wired bridges. <ref_snippet file="C:\Users\\Robby\Windsurf Projects\random_stuff\raspberry-pi_homephone\LIVI\src\main\services\projection\driver\aa\AaManager.ts" lines="158-163" />
- Held sessions should be kept in `SessionManager` but you probably want to **pause their video decode** (stop reading their sockets) to save USB bandwidth and CPU; otherwise the sockets back-pressure. A simpler v1: keep only one AA session “hot” (the active one) and let held phones fall back to charging-only, reconnecting on slot tap. This avoids deep AA-stack changes.

**Practical v1 path:** one active wired AA session at a time, plus a sidecar for ring detection. That gives you the tab UX and the “phone rings on hub” goal without rewriting the AA concurrency model.

## Where this fits into the gameplan

### Phase 1 — Android Auto core (now)
1. Apply the `config.json` projection/carName fix.
2. Verify map/toolbar drag and single-phone calls.
3. Add USB speakerphone and confirm call audio routes through the hub.

### Phase 1.5 — Multi-device foundation (new)
1. Identify USB topology for each dock slot (`lsusb -t` on the Pi, or a per-slot powered hub with port labels).
2. Customize `Home.tsx` to show Slot 1 / Slot 2 cards and use `selectDevice` for switching.
3. Test tab switching with one phone (tap re-activates the same session).
4. Build the Tasker → Pi HTTP ring prototype for one phone.

### Phase 2 — Concurrent sessions & calls
1. Patch `USBService`/`TransportArbiter` to allow two wired phones to be held.
2. Test two Android phones docked and switching by tab.
3. Replace Tasker with the companion app for call/notification forwarding.
4. Add “Answer on home” banner, larger answer/hangup buttons, family mode.

### Phase 3 — iPhone / CarPlay
- CarPlay becomes another protocol in the slot cards. `DeviceController` already understands `protocol: 'carplay'`. Test Android ↔ iPhone switching.

### Phase 4 — Scale / Enclosure
- 4 docks, powered hub topology, case, backup image, README.

## README.md updates to make
Add a **“Multi-device / dock slots”** section covering:
- How slots map to USB ports/hubs.
- Why `Home.tsx` is the tab UI, and how to customize it.
- The Android Auto single-session limitation and why a sidecar is needed for ring/notify.
- Tasker vs companion-app sidecar decision.
- Call flow: phone rings → sidecar notifies Pi → hub plays tone and highlights tab → user taps tab → session switches → `acceptPhone`.

This keeps the project realistic: you are not fighting Android Auto to be a multi-user switcher; you are using LIVI for what it does well (session switching and the dashboard) and adding a small per-phone helper for the one thing AA refuses to do (cross-session call awareness).