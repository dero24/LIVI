#!/bin/bash
# Put the Pi side in a clean state so LIVI can grab the phone
# before Android Auto on the phone has a chance to auto-start.
set -e

BUS_PORT="3-2"  # adjust if your phone is on a different USB port

echo "[clean-aa] Stopping LIVI and the health watchdog (so it doesn't restart behind us)..."
systemctl --user stop livi.service || true
systemctl --user stop livi-health.timer || true
systemctl --user stop livi-health.service || true
pkill -9 -f livi-compositor || true
pkill -9 -f '/home/raspberry/LIVI/extracted/livi' || true
sleep 2

echo "[clean-aa] Cycling USB port $BUS_PORT..."
echo 0 | sudo tee "/sys/bus/usb/devices/$BUS_PORT/authorized" >/dev/null
sleep 1
echo 1 | sudo tee "/sys/bus/usb/devices/$BUS_PORT/authorized" >/dev/null
sleep 1

echo "[clean-aa] ---------------------------------------------------------------"
echo "[clean-aa] NOW: on your phone, force-stop the Android Auto app."
echo "[clean-aa]      (Settings > Apps > Android Auto > Force stop)"
echo "[clean-aa] If force-stop doesn't help, reboot the phone instead."
echo "[clean-aa] Then plug the phone into the Pi and press Enter here."
echo "[clean-aa] ---------------------------------------------------------------"
read -r

echo "[clean-aa] Starting LIVI (it should see the phone in normal mode and do AOAP handshake)."
systemctl --user start livi.service

echo "[clean-aa] Done. Check the display and run:"
echo "[clean-aa]   systemctl --user status livi.service -l -n 40 --no-pager"
