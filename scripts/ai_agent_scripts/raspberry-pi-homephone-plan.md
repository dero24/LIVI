NOTE: THIS FILE DESCRIBES THE CONCEPT BUT SOME SOFTWARE IS IS OUTDATED. Please see the README.md for the latest information.

# Raspberry Pi 5 + CarPlay/Android Auto Home Phone Station

## Overview

Build a modern touchscreen home phone using your existing CarPlay dongle, a Raspberry Pi 5, and a touchscreen. The system mirrors your phone's CarPlay (or Android Auto) interface—calls, texts, maps, music, Siri—onto a countertop station. When your phone rings, the home station rings. You can answer/make calls and send texts all from the touchscreen.

---

## Hardware You Have

| Component | Notes |
|-----------|-------|
| **Raspberry Pi 5** | 4GB or 8GB recommended. Massively overpowered for this—great for smooth 60fps UI |
| **CarPlay dongle** | Likely a Carlinkit CPC200-CCPA or similar. Confirm the exact model |
| **Touchscreen** | Confirm size/resolution. 7" official Pi display or a USB HDMI touch panel both work |

## Hardware You Need

| Component | Est. Cost | Purpose |
|-----------|-----------|---------|
| **USB speakerphone** (e.g., Jabra Speak 410/510, or Anker PowerConf) | $30–80 | Combined speaker + microphone for calls. Speakerphone-style devices have echo cancellation built in, crucial for hands-free calls |
| **USB-C power supply** (official Pi 5, 27W / 5V 5A) | $12 | Since this is home use, just a wall plug—no DC-DC converter needed |
| **MicroSD card** (32GB+ endurance rated) | $10–15 | Samsung PRO Endurance or SanDisk High Endurance recommended |
| **Powered USB hub** (for multi-phone expansion) | $15–25 | Needed later when you add a second dongle for a second phone |
| **Case / stand** | $10–30 | Desktop stand or 3D-printed enclosure to make it look like a home phone |
| **Optional: second Carlinkit dongle** | $50–80 | For multi-phone tab switching (Phase 2) |

**Estimated additional spend: ~$60–130 for Phase 1**

---

## Software Options (Ranked for Your Use Case)

### Option A: **React-CarPlay** ⭐ RECOMMENDED

- **GitHub**: https://github.com/rhysmorgan134/react-carplay
- **What it is**: Open-source React/TypeScript app that runs natively on Raspberry Pi OS (no Android layer needed)
- **Pros**:
  - Runs on native Raspberry Pi OS (Bookworm) — lightweight, fast boot
  - 60fps @ 1080p on Pi 5
  - Built-in microphone device selection (pick your USB speakerphone)
  - Configurable key bindings
  - Auto-start on boot via systemd
  - Active community, 23+ releases
  - Uses `node-carplay` library underneath — hackable in TypeScript/JS
  - **Easiest to customize** since it's a React web app you can fork
- **Cons**:
  - CarPlay only (no Android Auto out of the box)
  - Single dongle/phone at a time in stock form
- **Why it's best for you**: Since you want customizability and already have a CarPlay dongle, this is the most hackable option. The React codebase means you can add a tab-switching UI for multiple phones yourself.

### Option B: **FastCarPlay**

- **GitHub**: https://github.com/niellun/FastCarPlay
- **What it is**: Lightweight C++ CarPlay AND Android Auto receiver
- **Pros**:
  - Supports **both CarPlay and Android Auto** natively
  - Very lightweight—runs even on Pi Zero 2W
  - Hardware-accelerated video decoding
  - Microphone/Siri/calls supported
- **Cons**:
  - Newer project, less mature UI
  - No built-in method to switch between wireless devices yet (on their roadmap)
  - C++ = harder to customize the UI vs React
- **Why consider**: If you want Android Auto backward compatibility day one, this is your best bet.

### Option C: **pi-carplay**

- **GitHub**: https://github.com/RGreeneRI/pi-carplay
- **What it is**: Electron-based, supports CarPlay + Android Auto
- **Pros**:
  - Cross-platform (Linux ARM, x86, macOS)
  - Supports both protocols
  - Clean Electron app
- **Cons**:
  - Android Auto requires pre-provisioning on another head unit first
  - Heavier than FastCarPlay
- **Why consider**: Good middle ground if you want both protocols with a JS-based app.

### Option D: **LineageOS (Full Android)**

- Run Android 14/15 on the Pi via KonstaKANG LineageOS builds
- Install the official Carlinkit APK
- **Pros**: Full Android ecosystem, Google Play, any app
- **Cons**: Heavy, slower boot, overkill for a home phone station, SwiftShader renderer workaround needed
- **Why skip**: Unnecessary overhead for home use where you just want calls/texts/music

---

## Recommended Architecture

```
┌─────────────────────────────────────────────┐
│           Raspberry Pi 5 (Home Station)     │
│                                             │
│  ┌──────────────────────────────────────┐   │
│  │  React-CarPlay (or FastCarPlay)      │   │
│  │  - Renders CarPlay/AA interface      │   │
│  │  - Handles touch input               │   │
│  │  - Routes audio to USB speakerphone  │   │
│  └──────────────────────────────────────┘   │
│                                             │
│  USB Port 1: Carlinkit Dongle (Phone A)     │
│  USB Port 2: USB Speakerphone               │
│  USB Port 3: (Future) Carlinkit #2 (Phone B)│
│  Display:    Touchscreen via HDMI/DSI       │
│  Power:      USB-C 27W wall adapter         │
│                                             │
│  WiFi/BT:    Connects wirelessly to phones  │
│              sitting anywhere in the house   │
└─────────────────────────────────────────────┘

Your iPhone/Android sits in another room or your pocket.
The Carlinkit dongle pairs via WiFi + Bluetooth.
When a call comes in → CarPlay rings → Pi speaker rings.
You answer on the touchscreen → talk through the speakerphone.
```

---

## Phase 1: Basic Single-Phone Home Station

### Step 1: Flash Raspberry Pi OS
1. Download **Raspberry Pi OS (64-bit, Desktop)** — Bookworm
2. Flash to microSD with Raspberry Pi Imager
3. Boot, connect to your home WiFi, update: `sudo apt update && sudo apt upgrade -y`

### Step 2: Install React-CarPlay
```bash
git clone https://github.com/rhysmorgan134/react-carplay.git
cd react-carplay
./setup-pi.sh
```
This handles:
- USB permissions (udev rules for Carlinkit vendor ID `1314`)
- Downloads the latest AppImage
- Creates autostart entry (launches on boot)
- Creates desktop shortcut

### Step 3: Plug In Hardware
1. Plug **Carlinkit dongle** into USB port
2. Plug **USB speakerphone** into another USB port
3. Connect **touchscreen** (HDMI + USB touch, or DSI ribbon cable)
4. Power on with USB-C adapter

### Step 4: Pair Your Phone
1. Launch React-CarPlay (auto-starts on boot)
2. On your iPhone: Go to **Settings → General → CarPlay**
3. The Carlinkit dongle will appear as a wireless CarPlay device
4. Pair via Bluetooth, then it connects over WiFi
5. ~17–26 seconds to connect (auto-reconnects in the future)

### Step 5: Configure Audio
1. In React-CarPlay settings, select your USB speakerphone as the **microphone device**
2. Audio output routes through the speakerphone automatically
3. Test: Make a call, verify you can hear and be heard

### Step 6: Home Phone Behavior
Once paired, your phone can be anywhere in WiFi/BT range (~30–50 ft):
- **Incoming call** → CarPlay UI shows the call → speaker rings/plays ringtone
- **Tap "Answer"** on touchscreen → speakerphone activates
- **Texts** → CarPlay shows notification → tap to have Siri read/reply
- **Music/Podcasts** → plays through the speakerphone or any connected speaker
- **Maps/Navigation** → displayed on screen (useful if prepping directions)
- **Siri** → "Hey Siri" through the speakerphone mic or tap-and-hold

### Step 7: Auto-Boot as Home Phone
React-CarPlay's setup script already creates an autostart entry. Additional polish:
```bash
# Hide mouse cursor after inactivity
sudo apt install unclutter
# Add to autostart
echo "@unclutter -idle 3" >> ~/.config/lxsession/LXDE-pi/autostart

# Prevent screen blanking
sudo raspi-config  # → Display Options → Screen Blanking → Off

# Optional: auto-login to desktop
sudo raspi-config  # → System Options → Boot → Desktop Autologin
```

---

## Phase 2: Multi-Phone Tab Switching

This is the expansion you described—hooking up multiple phones and selecting via tabs.

### Approach A: Multiple Carlinkit Dongles + Custom UI (Best)

1. **Buy a second Carlinkit dongle** ($50–80)
2. **Use a powered USB hub** to connect both dongles to the Pi
3. **Fork React-CarPlay** and add a tab-switching UI:
   - Each dongle gets its own `node-carplay` instance
   - Tab bar at the top: `[📱 Robby's iPhone] [📱 Perry's iPhone]`
   - Switching tabs pauses one CarPlay stream and activates the other
   - Incoming call on either phone shows a notification badge on its tab
   - The `node-carplay` npm package handles the USB communication—each dongle has a unique USB device path

**Technical approach for the custom UI:**
```
react-carplay (forked)
├── src/
│   ├── PhoneTabBar.tsx       ← New: tab UI for switching phones
│   ├── CarPlayInstance.tsx   ← New: wraps a single dongle connection
│   ├── NotificationBadge.tsx ← New: shows incoming call/text badge
│   └── App.tsx               ← Modified: manages multiple instances
```

The underlying `node-carplay` library already handles USB device enumeration. You'd:
- Detect multiple dongles by USB device path
- Create separate carplay sessions for each
- Only render the active session's video stream
- But keep audio monitoring on all sessions (so you hear ANY phone ring)

### Approach B: Carlinkit 2Air Dongle (Simpler, Limited)

The **Carlinkit 5.0 (2Air)** supports both CarPlay AND Android Auto on one dongle. To switch:
- Turn off BT/WiFi on Phone A → Phone B auto-connects
- This is manual and clunky—not great for a home phone

### Approach C: LineageOS with Split-Screen (Heavyweight)

Run full Android with two Carlinkit app instances in split-screen. Possible but laggy and complex.

**Recommendation: Approach A** — it gives you real tab switching with simultaneous monitoring.

---

## Phase 3: Polish & Expansion Ideas

### Better Audio
- **Upgrade to a Bluetooth speaker** for music (route CarPlay audio to a nice speaker)
- **Add a dedicated ring speaker** (e.g., a small buzzer or loud speaker that activates on incoming calls via a script)

### Physical Phone Feel
- **3D-print a dock** that looks like a modern home phone with the touchscreen angled
- **Add a physical handset** — USB phone handsets exist (~$15) that work as USB audio devices; configure as the call audio device for a real phone feel

### Wall-Mount Option
- Mount the touchscreen on the kitchen wall
- Run a flat USB-C cable to a hidden Pi behind the wall
- Clean, iPad-like home phone experience

### Android Auto Compatibility
If you want to support both iPhone and Android family members:
- Use **FastCarPlay** instead of React-CarPlay (supports both protocols)
- Or run two separate software instances: React-CarPlay for iPhones, OpenAuto Pro for Androids
- The **Carlinkit CPC200-CCPA** dongle supports both CarPlay (wired+wireless) and Android Auto (wired) — check your specific dongle model

### Multiple Rooms (Future)
- Deploy additional Pi + screen + dongle stations in other rooms
- All paired to the same phones — when one answers, the others stop ringing
- This mirrors how traditional multi-extension home phones worked

### Home Automation Integration
- Since the Pi runs Linux, add Home Assistant alongside
- "Hey Siri, turn off the lights" works through CarPlay → HomeKit

---

## Quick Reference: Software Comparison

| Feature | React-CarPlay | FastCarPlay | pi-carplay | LineageOS |
|---------|--------------|-------------|------------|-----------|
| CarPlay | ✅ | ✅ | ✅ | ✅ |
| Android Auto | ❌ | ✅ | ✅ (needs pre-pair) | ✅ |
| Runs on Pi OS | ✅ | ✅ | ✅ | ❌ (is Android) |
| Performance on Pi 5 | 60fps 1080p | 60fps 1080p | 60fps 1080p | 30fps typically |
| Customizable UI | ⭐⭐⭐ (React/TS) | ⭐ (C++) | ⭐⭐ (Electron) | ⭐ |
| Mic support | ✅ | ✅ | ✅ (needs SoX) | ✅ |
| Auto-start | ✅ | ✅ | ✅ | Manual config |
| Multi-dongle ready | Hackable | On roadmap | Not yet | Via Android |
| Boot time | ~15–20s | ~10–15s | ~15–20s | ~45–60s |
| Home use friendly | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐ |

---

## Important Notes

1. **WiFi range**: The Carlinkit dongle creates its own WiFi hotspot to talk to your phone. Range is typically 30–50 feet. Your phone does NOT need to be plugged in or near the station.

2. **CarPlay apps available**: Phone, Messages, Maps, Music, Podcasts, Spotify, Waze, WhatsApp, Telegram, Signal, Google Maps, Audible, and 600+ CarPlay-compatible apps. All work through the home station.

3. **No car required**: The Carlinkit dongle doesn't know or care that it's not in a car. It emulates a CarPlay head unit. The Pi is the "car stereo" as far as Apple is concerned.

4. **Incoming calls WILL ring**: CarPlay's call UI takes over the screen when a call comes in. The ringtone plays through whatever audio output you've configured (your USB speakerphone). This is native CarPlay behavior.

5. **Texts work via Siri**: CarPlay doesn't show a keyboard for safety (designed for cars). You compose texts via Siri voice dictation. For home use, you could potentially add a keyboard overlay in your forked React-CarPlay UI, though this would be custom development.

6. **Power consumption**: ~10–15W total for the whole station. Perfectly fine to leave on 24/7.

7. **Heat**: Non-issue for home use. No hot car dashboard to worry about. A passive case or the official Pi 5 active cooler is plenty.

---

## Getting Started Checklist

- [ ] Confirm your Carlinkit dongle model (check label or `lsusb` output)
- [ ] Confirm your touchscreen model and connection type (HDMI+USB or DSI)
- [ ] Get a USB speakerphone (Jabra Speak 410 is a solid budget pick ~$30 used)
- [ ] Get official Raspberry Pi 5 USB-C power supply (27W)
- [ ] Get a 32GB+ endurance microSD card
- [ ] Flash Raspberry Pi OS 64-bit Desktop (Bookworm)
- [ ] Install React-CarPlay via setup script
- [ ] Pair your iPhone
- [ ] Test calls, texts, music, Siri
- [ ] Configure auto-boot, hide cursor, disable screen blanking
- [ ] (Phase 2) Get second dongle + powered USB hub for multi-phone
- [ ] (Phase 2) Fork React-CarPlay, add tab-switching UI

---

## Key Links

- **React-CarPlay**: https://github.com/rhysmorgan134/react-carplay
- **node-carplay** (underlying lib): https://github.com/rhysmorgan134/node-CarPlay
- **FastCarPlay** (CarPlay + AA): https://github.com/niellun/FastCarPlay
- **pi-carplay** (CarPlay + AA Electron): https://github.com/RGreeneRI/pi-carplay
- **KonstaKANG LineageOS** (if you want Android): https://konstakang.com/devices/rpi5/LineageOS22/
- **Carlinkit official**: https://www.carlinkit.com/
