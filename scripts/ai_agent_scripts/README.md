# Raspberry Pi Home Phone Hub

A countertop touchscreen station that docks 2+ phones, lets you switch between them, and handles calls, texts, maps, and media through a single home interface. Scales to 4 docks.

**Recommended stack:** [LIVI](https://github.com/f-io/LIVI) on a Raspberry Pi 5 running Raspberry Pi OS Trixie.

---

## What it does

- Docks 2 phones for the prototype, charging continuously.
- One touchscreen shows tabs/selection for each docked phone.
- Place/receive calls and messages, maps, music, and voice assistant through the hub.
- Later, scale the same design to 4 dock slots.

LIVI supports native Android Auto (wired + wireless on Linux) and CarPlay (wired + wireless, but CarPlay needs an MFi authentication path).

---

## Hardware

### Core
- **Raspberry Pi 5** (4GB or 8GB) + official 27W USB-C PSU.
- **Touchscreen** — DSI ribbon or HDMI + USB touch. Any screen that "just works" on Linux.
- **Powered USB hub(s)** — critical for stable data + charging to multiple docks.
- **USB microphone or USB speakerphone** for calls (e.g. Jabra Speak, Anker PowerConf).
- **Audio output** — HDMI audio, USB speakerphone, or an audio/DAC HAT. **Pi 5 has no 3.5mm jack.**
- Quality microSD card (32GB+ endurance recommended).

### Dock subsystem (prototype = 2 slots)
- Two phone slots with fixed mechanical alignment.
- Correct charging connector per phone (Lightning vs USB-C).
- Short, high-quality USB cables from hub → dock, with strain relief.
- Optional: status LED per slot (Connected / Charging / Needs attention).
- Thermal/venting if running heavier charging loads.

### Wiring summary
- Pi 5 ← powered USB hub ← dock cables ← phones.
- Touchscreen to Pi (DSI or HDMI+USB touch).
- USB mic/speakerphone into Pi or hub.

---

## Software setup

### 1. Flash the OS
LIVI needs **OpenGL ES 3.x**, so Pi 4/5/CM4/CM5 must use **Raspberry Pi OS Trixie (Debian 13) 64-bit**.

- **Raspberry Pi Imager:** https://www.raspberrypi.com/software/  
  Windows exe: https://downloads.raspberrypi.com/imager/imager-1.9.6.exe
- **Trixie 64-bit Desktop image:**  
  https://downloads.raspberrypi.org/raspios_arm64/images/raspios_arm64-2026-06-19/2026-06-18-raspios-trixie-arm64.img.xz
- **Trixie 64-bit Lite image** (headless kiosk):  
  https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2026-06-19/2026-06-18-raspios-trixie-arm64-lite.img.xz

Flash, boot, then update:

```bash
sudo apt update && sudo apt full-upgrade -y
```

### 2. Install LIVI

**Desktop install** (recommended for first build):

```bash
curl -fL -o install.sh https://raw.githubusercontent.com/f-io/LIVI/main/scripts/install/desktop/install.sh
chmod +x install.sh
./install.sh
```

**Headless/Lite install** (true kiosk):

```bash
curl -fL -o install.sh https://raw.githubusercontent.com/f-io/LIVI/main/scripts/install/headless/install.sh
chmod +x install.sh
./install.sh
sudo reboot
```

The installer downloads the AppImage, patches GStreamer/HEVC if needed, writes udev rules, and sets autostart.

### 3. Installer prompts
- **MFi overlay** — choose `N` unless you have an MFi coprocessor wired to the Pi I²C bus or are using native CarPlay.
- **RGB/VGA display below HDMI clock floor** — choose `N` unless your HDMI touchscreen is blank and needs the `vc4` driver rebuilt.

### 4. First boot
- Reboot.
- On first launch, accept the udev rule prompt so LIVI can access USB phones/dongles.
- Desktop install: LIVI autostarts. Disable screen blanking with `sudo raspi-config` → Display → Screen Blanking → Off.
- Headless install: LIVI owns `tty1` via `livi-kiosk.service`.

---

## Pairing a phone

### Android Auto (start here)
1. Enable Developer Options + USB debugging on the Android phone.
2. Plug a quality data cable from the dock to the powered hub/Pi.
3. LIVI should start the Android Auto session on the touchscreen.

No dongle is needed for Android Auto.

### iPhone / CarPlay
CarPlay requires Apple MFi authentication. You have two options:

**A. Carlinkit dongle (recommended, easiest)**
- Supported models: **CPC200-CCPA** (wireless/wired) and **CPC200-CCPW** (wired).
- Product page: https://www.carlinkit.com/ccpa
- Plug the dongle into the hub, then on the iPhone go to **Settings → General → CarPlay** and pair via Bluetooth + Wi-Fi.

**B. Native CarPlay with MFi coprocessor**
- Add to `/boot/firmware/config.txt`:
  ```ini
  dtoverlay=i2c-gpio,bus=2,i2c_gpio_sda=19,i2c_gpio_scl=26,i2c_gpio_delay_us=50
  ```
- In LIVI config set `carPlayMfiI2cBus: 2` and `carPlayMfiPowerGpio: 21`.
- Details: https://github.com/f-io/LIVI/blob/main/README.md#mfi-authentication
- Ready-made HAT option: https://github.com/signalius/MFI_Chip_Rpi_Hat

---

## Audio

Pi 5 has no 3.5mm AUX jack. Pick one path:

- **USB speakerphone** — simplest; handles mic + speaker + echo cancellation.
- **USB microphone** + HDMI audio or audio/DAC HAT.
- Bluetooth speakers/mic work but can add latency and dropouts for calls.

In **LIVI → Settings → Audio**, set:
- **Output:** your speaker/HDMI/HAT.
- **Input:** your USB microphone.

---

## Build phases

### Phase 1 — Android-only prototype (2 docks)
Goal: prove the stack works end-to-end.

1. Install LIVI, connect Phone A to Dock Slot 1, Phone B to Dock Slot 2.
2. Verify:
   - phones charge
   - Android Auto sessions appear
   - switching between sessions works
   - calls work with chosen mic + audio out

**Acceptance criteria**
- Dock Phone A, see it, make/receive a call.
- Dock Phone B, see it, switch to it, make/receive a call.
- No frequent disconnect/reconnect loops.

### Phase 2 — Household polish
- Build a home screen with 2 phone cards (Slot 1 / Slot 2), "Now Active" indicator, quick actions (Call, Messages, Maps, Media).
- Add reliability engineering:
  - USB disconnect/reconnect resilience
  - UI watchdog / auto-restart
  - "last known good state" fallback
  - clear on-screen slot status (loose cable, not connected, etc.)
- Optional family safety mode: larger buttons, fewer steps to answer a call.

### Phase 3 — Add iPhone
Do this only after Android is rock solid.

1. Choose Carlinkit dongle or MFi coprocessor path.
2. Verify:
   - iPhone session launches on the touchscreen
   - calls/texts behave correctly
   - switching between Android and iPhone sessions works in the tab model

### Phase 4 — Scale to 4 docks
- Use a proper powered hub topology sized for both data stability and burst charging current.
- Keep dock connectors identical where possible.
- Hide/route cables cleanly as slots increase.
- UI: move from 2 to 4 phone cards; keep it as simple as Slot 1–4 tabs + Active.

---

## Bottlenecks & de-risk

| Risk | Mitigation |
|------|------------|
| **USB reliability** | Overbuilt powered hubs, short cables, strain relief, precise slot alignment. |
| **iPhone CarPlay auth** | Treat iPhone as a separate milestone. Use Carlinkit for simplicity. |
| **Audio / mic placement** | Choose placement that works for all users, then lock it. |
| **App notifications** | Ignore custom notification sounds; core flows (calls/messages/media/maps) are already strong. |

---

## Recovery (re-flash / start over)

If the Pi stops booting or the display goes blank during rotation, the SD card is likely corrupted. Re-flash Raspberry Pi OS Trixie 64-bit, then:

1. **Boot and enable SSH** (via imager advanced options or `raspi-config`).
2. **Copy the AppImage and run the setup script** from this repo:
   ```bash
   scp -r raspberry@<pi-ip>:/dev/null .
   # On the Pi:
   mkdir -p ~/LIVI ~/.config
   # Copy LIVI-8.0.0-linux-arm64.AppImage into /home/raspberry/LIVI/
   chmod +x /home/raspberry/LIVI/LIVI.AppImage
   # Copy setup-pi.sh and run it
   bash setup-pi.sh
   ```
3. **Reboot** and verify:
   - Display is `600x1024` portrait.
   - Touch moves the cursor and taps register.
   - LIVI shows the Home Hub with phone cards.
   - Plugging in the Android phone starts Android Auto.

To switch the Pi back to the normal Raspberry Pi Desktop session:
```bash
sudo sed -i 's/^user-session=.*/user-session=rpd-x/' /etc/lightdm/lightdm.conf
sudo sed -i 's/^autologin-session=.*/autologin-session=rpd-x/' /etc/lightdm/lightdm.conf
sudo reboot
```
To go back to the LIVI/labwc session:
```bash
sudo sed -i 's/^user-session=.*/user-session=rpd-labwc/' /etc/lightdm/lightdm.conf
sudo sed -i 's/^autologin-session=.*/autologin-session=rpd-labwc/' /etc/lightdm/lightdm.conf
systemctl --user enable livi.service
systemctl --user start livi.service
sudo reboot
```

---

## Quick reference links

- **LIVI:** https://github.com/f-io/LIVI
- **LIVI releases:** https://github.com/f-io/LIVI/releases
- **LIVI MFi auth docs:** https://github.com/f-io/LIVI/blob/main/README.md#mfi-authentication
- **Carlinkit CPC200-CCPA:** https://www.carlinkit.com/ccpa
- **MFi RPi HAT:** https://github.com/signalius/MFI_Chip_Rpi_Hat
- **Raspberry Pi OS Trixie:** https://www.raspberrypi.com/software/operating-systems/
- **Raspberry Pi Imager:** https://www.raspberrypi.com/software/

Start with one Android phone over USB. Once that is solid, add the second dock, then the iPhone path, then scale to four.
