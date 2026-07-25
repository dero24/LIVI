We are building a Raspberry Pi 5 countertop home phone hub using the LIVI open-source Android Auto / CarPlay host. The custom portrait Home.tsx UI is in this repo. The Pi is newly flashed with Raspberry Pi OS Trixie 64-bit.

High-level build flow from a fresh image:

1. LIVI install (Phase 1)
   - Either run the upstream LIVI install.sh from f-io/LIVI, OR manually place the pre-built AppImage at /home/raspberry/LIVI/LIVI.AppImage.
   - The CI pipeline for this project produces the AppImage (arm64) and the custom setup-pi.sh deploys the runtime configuration.

2. Runtime configuration (Phase 2)
   - Run /home/raspberry/setup-pi.sh as the raspberry user.
   - It sets up:
     - labwc Wayland session with lightdm autologin
     - portrait display output (kanshi / wlr-randr 1024x600 rotated to 600x1024)
     - touch as a mouse pointer in labwc (mouseEmulation + libinput calibrationMatrix)
     - LIVI config for 600x1024 portrait and startPage=home
     - udev rules for Samsung/Google cdc_acm unbind and WCH touch controller
     - systemd user service + health watchdog for LIVI
   - Reboot.

3. First functional test: touch
   - After boot, LIVI should be in vertical/portrait mode.
   - Touch the screen. Does the cursor follow your finger? Do taps register on the home UI?
   - If touch does NOT work, stop. Debug labwc rc.xml touch/calibrationMatrix, libinput list-devices, wlr-randr output transform, and wev/libinput debug-events before moving on.

4. Second functional test: Android Auto
   - Only after touch is reliable, plug in the Android phone with USB debugging enabled.
   - Verify Android Auto starts and appears on the home hub.
   - Check LIVI status data or logs if it does not connect.

Do not proceed to Android Auto until touch works. If anything in setup-pi.sh needs to change, edit the script and re-run before testing.