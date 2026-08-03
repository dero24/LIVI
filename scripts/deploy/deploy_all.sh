#!/bin/bash
# One-shot deploy: rtw88/wlan0 stability fixes + app updates.
# Runs on the Pi. Expects files already uploaded:
#   /tmp/rtw88-stability.conf, /tmp/zz-wifi-powersave-off.conf
#   /home/raspberry/homephone-sidecar.py, patch_homehub_v2.py, hfp_call_monitor.py
set -x

# === 1. rtw88 deep-LPS fix (the hang trigger) ===
echo pi | sudo -S install -m 0644 -o root -g root /tmp/rtw88-stability.conf /etc/modprobe.d/rtw88-stability.conf

# === 2. NetworkManager power-save off (wlan0 unreachability + rtw88 trigger #2) ===
echo pi | sudo -S install -m 0644 -o root -g root /tmp/zz-wifi-powersave-off.conf /etc/NetworkManager/conf.d/zz-wifi-powersave-off.conf
echo pi | sudo -S systemctl reload NetworkManager

# === 3. Runtime power_save off for current session (keeps SSH alive NOW) ===
iw dev wlan0 set power_save off 2>/dev/null || echo pi | sudo -S iw dev wlan0 set power_save off
iw dev wlan0 get power_save

# === 4. Persistent journald (so we can diagnose the NEXT hang from -b -1) ===
echo pi | sudo -S mkdir -p /var/log/journal
echo pi | sudo -S systemd-tmpfiles --create --prefix /var/log/journal 2>/dev/null
echo pi | sudo -S systemctl restart systemd-journald

# === 5. Record existing dongle udev rule + autosuspend state ===
cat /etc/udev/rules.d/99-usb-dongle-power.rules 2>/dev/null
cat /sys/module/usbcore/parameters/autosuspend

# === 6. App deploy: sidecar + hfp monitor + overlay patch ===
python3 -m py_compile /home/raspberry/homephone-sidecar.py /home/raspberry/hfp_call_monitor.py /home/raspberry/patch_homehub_v2.py && echo SYNTAX-OK
systemctl --user restart homephone-sidecar.service
systemctl --user restart hfp-call-monitor.service
sleep 2
systemctl --user is-active homephone-sidecar.service hfp-call-monitor.service
python3 /home/raspberry/patch_homehub_v2.py 2>&1 | grep -E 'Patched|WARNING|Trimmed|Appended|Done' | head -10
systemctl --user restart livi.service
sleep 15
systemctl --user is-active livi.service
echo '=== DEPLOY-ALL DONE ==='
