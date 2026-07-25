#!/bin/bash
set -e

WAIT_SECONDS="${1:-60}"

run_sudo() {
  if [ -n "$SUDO_PASS" ]; then
    echo "$SUDO_PASS" | sudo -S "$@"
  else
    sudo "$@"
  fi
}

echo "[clean-aa] Stopping LIVI and watchdog..."
systemctl --user stop livi.service || true
systemctl --user stop livi-health.timer || true
systemctl --user stop livi-health.service || true
pkill -9 -f livi-compositor || true
pkill -9 -f '/home/raspberry/LIVI/extracted/livi' || true
sleep 2

echo "[clean-aa] Disabling phone USB buses (keep usb1 touch/keyboard alive)..."
for bus in usb2 usb3 usb4; do
  if [ -e "/sys/bus/usb/devices/$bus/authorized" ]; then
    run_sudo sh -c "echo 0 > /sys/bus/usb/devices/$bus/authorized" || true
  fi
done
sleep 1

echo "[clean-aa] Re-enabling phone USB buses..."
for bus in usb2 usb3 usb4; do
  if [ -e "/sys/bus/usb/devices/$bus/authorized" ]; then
    run_sudo sh -c "echo 1 > /sys/bus/usb/devices/$bus/authorized" || true
  fi
done
sleep 1

echo "[clean-aa] ---------------------------------------------------------------"
echo "[clean-aa] NEXT $WAIT_SECONDS SEC:"
echo "[clean-aa]   1. Force-stop Android Auto on your phone."
echo "[clean-aa]   2. Plug the phone into the Pi."
echo "[clean-aa] LIVI will start automatically after the delay."
echo "[clean-aa] ---------------------------------------------------------------"
sleep "$WAIT_SECONDS"

echo "[clean-aa] Starting LIVI..."
systemctl --user start livi.service

echo "[clean-aa] Done. Check:"
echo "[clean-aa]   systemctl --user status livi.service -l -n 40 --no-pager"
