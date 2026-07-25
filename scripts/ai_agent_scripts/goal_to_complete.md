Short answer: **Yes, the hub can switch to the ringing phone and answer there — but only with a sidecar (Tasker/app), because Android Auto itself will not tell us a non-active phone is ringing. We cannot modify the Android Auto protocol to be truly multi-session, but we can absolutely make LIVI feel like a multi-phone home dock.**

## Does it switch when another phone rings?

With the sidecar: **yes**.

The flow would be:

1. Phone in Slot 2 rings.
2. The Tasker profile / companion app on that phone sends `POST /ring?slot=2&caller=...` to the Pi.
3. The Pi plays a ringtone and flashes the Slot 2 card.
4. The user taps **Answer** on the touchscreen (or it auto-answers after a timeout you configure).
5. The Pi calls `selectDevice(slot2Id)`, which activates that session, then sends the `acceptPhone` command.

This switches the **hub screen** to that phone’s Android Auto session, so the call UI appears and the user can talk through the hub’s mic/speaker. It does not switch anything on the physical phone itself.

**Important UX choice:** I would *not* auto-switch instantly on every ring, because it would yank the screen away from someone who is actively using the hub. Better defaults:

- **Ring + banner**, tap to answer.
- Optional **“auto-switch on ring after 3–4 rings”** for an always-listening kitchen counter mode.

## Can we modify Android Auto to include multi-session?

No — not the Android Auto app on the phone. That is Google’s code and the protocol is built around one head-unit session per phone. LIVI is the head-unit side, so what we can modify is LIVI, and LIVI already has the right bones:

- `SessionManager` supports one active + multiple held sessions. <ref_snippet file="C:\Users\Robby\Windsurf Projects\random_stuff\raspberry-pi_homephone\LIVI\src\main\services\projection\services\SessionManager.ts" lines="27-37" />
- `DeviceController.selectDevice` activates a session. <ref_snippet file="C:\Users\Robby\Windsurf Projects\random_stuff\raspberry-pi_homephone\LIVI\src\main\services\projection\services\DeviceController.ts" lines="55-78" />
- `Home.tsx` is already a dashboard with device cards. <ref_snippet file="C:\Users\Robby\Windsurf Projects\random_stuff\raspberry-pi_homephone\LIVI\src\renderer\src\components\pages\home\Home.tsx" lines="131-144" />
- `AaManager` can hold multiple wired bridges keyed by device serial. <ref_snippet file="C:\Users\Robby\Windsurf Projects\random_stuff\raspberry-pi_homephone\LIVI\src\main\services\projection\driver\aa\AaManager.ts" lines="158-163" />

The hard limit is: **only one phone’s Android Auto video stream can be on screen at a time.** We cannot display two phones side-by-side in AA. But we can make switching between them very fast and context-aware.

## “Make it work amazingly” vs “good enough”

Given what you are building — a real countertop home phone hub where phones stay docked — **I recommend the “amazing” plan**. The extra work is not about breaking AA; it is about building the sidecar and polishing the session switching. It is worth it because:

- A companion app or Tasker is the only way to get **call/notification awareness for non-active phones**.
- LIVI’s multi-session switching is already there; we just need to extend `USBService`/`TransportArbiter` to support multiple **wired** phones and polish `Home.tsx`.
- The user experience you want — “phone rings, hub answers” — is only possible with the sidecar.

### What “amazing” looks like

1. **Dock-slot dashboard** in `Home.tsx`: Slot 1–4 cards with names, battery, signal, charging status, and “ringing” badge.
2. **Fast session switching**: tap a slot to instantly switch to that phone’s AA session.
3. **Companion app / Tasker**: on each phone, forwards incoming calls, texts, and selected notifications to the Pi.
4. **Ring/answer flow**: hub rings, highlights the slot, switches to that session on answer.
5. **Notification badges** for non-active phones so users know messages are waiting.
6. **Per-slot settings**: unique `carName` per dock slot so each phone gets its own AA layout.

### What “good enough” looks like

- Manual slot switching in `Home.tsx`.
- Tasker only for incoming-call ring detection.
- Non-active notifications ignored; user checks phones for those.

“Good enough” works as a prototype, but it does **not** deliver the “leave your phone on the hub” vision for calls and messages.

## My recommendation

Go with the **amazing-but-realistic** plan. Don’t try to modify Android Auto itself; instead build the best multi-session home dock on top of LIVI:

1. **Now**: apply the `config.json` display/carName fix and verify map/toolbar drag.
2. **Next**: slot mapping + `Home.tsx` dock cards.
3. **Then**: Tasker ring prototype (cheap proof).
4. **After**: refactor `USBService`/`TransportArbiter` for multiple wired phones.
5. **Later**: replace Tasker with a tiny companion app for caller ID, messages, and notification badges.

This gets you a product-grade experience without chasing the impossible (true concurrent AA video from multiple phones). The limitation is the AA protocol, not the coding models — and the workaround is exactly the sidecar + fast switching architecture.