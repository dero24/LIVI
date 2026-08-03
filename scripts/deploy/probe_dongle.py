#!/usr/bin/env python3
"""Probe WiFi dongle and wireless AA readiness on the Pi."""
import subprocess, os

print('=== USB devices ===')
r = subprocess.run(['lsusb'], capture_output=True, text=True, timeout=5)
print(r.stdout)

print('=== Network interfaces ===')
r = subprocess.run(['ip', 'addr'], capture_output=True, text=True, timeout=5)
# Filter to show just interface names and states
for line in r.stdout.split('\n'):
    if line.startswith(('1: ', '2: ', '3: ', '4: ', '5: ', '6: ', '7: ', '8: ')):
        print(line)
    elif 'inet ' in line or 'state ' in line:
        print('  ' + line.strip())

print()
print('=== WiFi interfaces (iw) ===')
r = subprocess.run(['iw', 'dev'], capture_output=True, text=True, timeout=5)
print(r.stdout)

print('=== wlan0 details ===')
r = subprocess.run(['iw', 'dev', 'wlan0', 'info'], capture_output=True, text=True, timeout=5)
print(r.stdout if r.stdout else '  (no wlan0)')

print('=== wlan1 details (if dongle) ===')
r = subprocess.run(['iw', 'dev', 'wlan1', 'info'], capture_output=True, text=True, timeout=5)
print(r.stdout if r.stdout else '  (no wlan1)')

print('=== Connected WiFi networks ===')
r = subprocess.run(['nmcli', '-t', '-f', 'NAME,DEVICE,TYPE,STATE', 'con', 'show'], capture_output=True, text=True, timeout=5)
print(r.stdout)

print('=== WiFi scan (wlan0) ===')
r = subprocess.run(['nmcli', 'dev', 'wifi', 'list', 'ifname', 'wlan0'], capture_output=True, text=True, timeout=10)
print(r.stdout[:500] if r.stdout else '  (none)')

print('=== WiFi scan (wlan1, if exists) ===')
r = subprocess.run(['nmcli', 'dev', 'wifi', 'list', 'ifname', 'wlan1'], capture_output=True, text=True, timeout=10)
print(r.stdout[:500] if r.stdout else '  (no wlan1 or no scan)')

print('=== Kernel modules (wifi-related) ===')
r = subprocess.run(['lsmod'], capture_output=True, text=True, timeout=5)
for line in r.stdout.split('\n'):
    if any(x in line.lower() for x in ['rtw', 'rtl', 'ath', 'cfg80211', 'mac80211', 'usb']):
        print(line)

print('=== dmesg USB/wifi (last 20 matches) ===')
r = subprocess.run(['dmesg'], capture_output=True, text=True, timeout=5)
lines = [l for l in r.stdout.split('\n') if any(x in l.lower() for x in ['usb', 'wifi', 'wlan', 'rtl', 'rtw', 'ath', 'adapter', 'dongle'])]
for line in lines[-20:]:
    print(line)

print('=== Android Auto / wireless AA deps ===')
# Check if LIVI has wireless AA support
r = subprocess.run(['which', 'adbd'], capture_output=True, text=True, timeout=5)
print(f'adbd: {r.stdout.strip() or "not found"}')
# Check for any AA-related config
r = subprocess.run(['find', '/home/raspberry', '-name', '*.json', '-path', '*/config/*'], capture_output=True, text=True, timeout=5)
print(f'Config files: {r.stdout.strip()}')

print('=== Current LIVI config ===')
try:
    import json
    with open('/home/raspberry/.config/LIVI/config.json') as f:
        cfg = json.load(f)
    for k, v in sorted(cfg.items()):
        print(f'  {k}: {v}')
except Exception as e:
    print(f'  Error: {e}')
