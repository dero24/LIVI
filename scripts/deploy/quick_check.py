#!/usr/bin/env python3
"""Check Pi status with dongle plugged in."""
import subprocess, time

print('=== Services ===')
for svc in ['livi.service', 'homephone-sidecar.service']:
    r = subprocess.run(['systemctl', '--user', 'is-active', svc],
                       capture_output=True, text=True, timeout=5)
    print(f'  {svc}: {r.stdout.strip()}')

print('=== Dongle ===')
r = subprocess.run(['lsusb'], capture_output=True, text=True, timeout=5)
for line in r.stdout.split('\n'):
    if '2357' in line or 'TP-Link' in line:
        print(f'  {line.strip()}')

r = subprocess.run(['ip', 'link', 'show', 'wlan1'], capture_output=True, text=True, timeout=5)
if r.stdout.strip():
    print(f'  wlan1: {r.stdout.strip()[:100]}')
else:
    print('  wlan1: not found')

print('=== Autosuspend ===')
r = subprocess.run(['cat', '/sys/module/usbcore/parameters/autosuspend'],
                   capture_output=True, text=True, timeout=5)
print(f'  autosuspend = {r.stdout.strip()}')

print('=== Settings page ===')
r = subprocess.run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', 'http://localhost:8123/settings'],
                   capture_output=True, text=True, timeout=5)
print(f'  HTTP status: {r.stdout.strip()}')

print('=== BT devices ===')
r = subprocess.run(['curl', '-s', 'http://localhost:8123/api/bluetooth/devices'],
                   capture_output=True, text=True, timeout=5)
import json
try:
    d = json.loads(r.stdout)
    for dev in d.get('devices', []):
        print(f'  {dev["name"]} | is_phone={dev.get("is_phone")} | connected={dev.get("connected")}')
    adp = d.get('adapter', {})
    print(f'  Adapter: {adp.get("name")} | powered={adp.get("powered")} | discoverable={adp.get("discoverable")}')
except:
    print(f'  Raw: {r.stdout[:200]}')

print('=== hostapd ===')
r = subprocess.run(['pgrep', '-a', 'hostapd'], capture_output=True, text=True, timeout=5)
print(f'  {r.stdout.strip() or "not running"}')

print('=== dmesg rtw88 (last 5) ===')
r = subprocess.run(['sudo', '-S', 'dmesg'], input='pi\n',
                   capture_output=True, text=True, timeout=5)
rtw = [l for l in r.stdout.split('\n') if 'rtw88' in l or 'wlan1' in l]
for line in rtw[-5:]:
    print(f'  {line.strip()}')
