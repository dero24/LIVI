#!/bin/bash
set -e

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

echo "[clean-aa] Pi side ready."
echo "[clean-aa] NOW: force-stop Android Auto on your phone, then plug the phone into the Pi."
echo "[clean-aa] When the phone is plugged and AA is force-stopped, run:"
echo "[clean-aa]   /home/raspberry/clean-aa-start.sh"
