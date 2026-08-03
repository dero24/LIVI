#!/usr/bin/env python3
"""Verify wired AA still works alongside wireless AA, and sidecar is healthy."""
import subprocess, json, os

# Check sidecar
print('=== Sidecar status ===')
r = subprocess.run(['systemctl', '--user', 'is-active', 'homephone-sidecar.service'],
                   capture_output=True, text=True, timeout=5)
print(f'  {r.stdout.strip()}')

# Check sidecar /status endpoint
print('=== Sidecar /status ===')
r = subprocess.run(['curl', '-s', 'http://localhost:8123/status'],
                   capture_output=True, text=True, timeout=5)
try:
    status = json.loads(r.stdout)
    print(f'  aa_connected: {status.get("aa_connected")}')
    print(f'  aa_transport: {status.get("aa_transport")}')
    print(f'  cp_connected: {status.get("cp_connected")}')
    print(f'  media present: {bool(status.get("media"))}')
    print(f'  notifs count: {len(status.get("notifs", []))}')
except:
    print(f'  Raw: {r.stdout[:200]}')

# Check USB-connected phone (wired AA)
print()
print('=== USB devices (looking for Android phone) ===')
r = subprocess.run(['lsusb'], capture_output=True, text=True, timeout=5)
for line in r.stdout.split('\n'):
    if 'Google' in line or 'Android' in line or '18d1' in line or '04e8' in line:
        print(f'  {line.strip()}')

# Check LIVI's AA session status via the overlay's status poll
print()
print('=== LIVI AA session (via sidecar) ===')
r = subprocess.run(['curl', '-s', 'http://localhost:8123/status'],
                   capture_output=True, text=True, timeout=5)
try:
    status = json.loads(r.stdout)
    # Check all AA-related fields
    for k, v in sorted(status.items()):
        if 'aa' in k.lower() or 'session' in k.lower() or 'phone' in k.lower() or 'transport' in k.lower():
            print(f'  {k}: {v}')
except:
    pass

# Check that wlan0 (home WiFi) is still connected
print()
print('=== wlan0 (home WiFi) ===')
r = subprocess.run(['ip', 'addr', 'show', 'wlan0'], capture_output=True, text=True, timeout=5)
for line in r.stdout.split('\n'):
    if 'inet ' in line or 'state ' in line:
        print(f'  {line.strip()}')

# Check that the sidecar can still reach the internet (via wlan0)
print()
print('=== Internet connectivity (via wlan0) ===')
r = subprocess.run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', '--max-time', '5', 'http://1.1.1.1'],
                   capture_output=True, text=True, timeout=10)
print(f'  HTTP status to 1.1.1.1: {r.stdout.strip()}')

# Check Bluetooth discoverable (needed for phone pairing)
print()
print('=== Bluetooth ===')
r = subprocess.run(['btmgmt', 'info'], capture_output=True, text=True, timeout=5)
print(r.stdout)

# Check if BT is discoverable (needed for first pairing)
r = subprocess.run(['hciconfig', 'hci0'], capture_output=True, text=True, timeout=5)
print(r.stdout)
