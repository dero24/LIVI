#!/usr/bin/env python3
"""Check wireless AA prerequisites."""
import subprocess, json, os

print('=== hostapd ===')
r = subprocess.run(['which', 'hostapd'], capture_output=True, text=True, timeout=5)
print(f'  path: {r.stdout.strip() or "NOT INSTALLED"}')
r = subprocess.run(['dpkg', '-l', 'hostapd'], capture_output=True, text=True, timeout=5)
for line in r.stdout.split('\n'):
    if 'hostapd' in line and 'ii' in line:
        print(f'  package: {line.strip()}')

print('=== dnsmasq ===')
r = subprocess.run(['which', 'dnsmasq'], capture_output=True, text=True, timeout=5)
print(f'  path: {r.stdout.strip() or "NOT INSTALLED"}')
r = subprocess.run(['dpkg', '-l', 'dnsmasq-base'], capture_output=True, text=True, timeout=5)
for line in r.stdout.split('\n'):
    if 'dnsmasq' in line and 'ii' in line:
        print(f'  package: {line.strip()}')

print('=== iw ===')
r = subprocess.run(['which', 'iw'], capture_output=True, text=True, timeout=5)
print(f'  path: {r.stdout.strip() or "NOT INSTALLED"}')

print('=== rfkill ===')
r = subprocess.run(['which', 'rfkill'], capture_output=True, text=True, timeout=5)
print(f'  path: {r.stdout.strip() or "NOT INSTALLED"}')

print('=== bluez ===')
r = subprocess.run(['dpkg', '-l', 'bluez'], capture_output=True, text=True, timeout=5)
for line in r.stdout.split('\n'):
    if 'bluez' in line and 'ii' in line:
        print(f'  package: {line.strip()}')

print('=== LIVI config (AA-related) ===')
try:
    with open('/home/raspberry/.config/LIVI/config.json') as f:
        cfg = json.load(f)
    for k in sorted(cfg.keys()):
        print(f'  {k}: {cfg[k]}')
except Exception as e:
    print(f'  Error: {e}')

print('=== LIVI version ===')
try:
    with open('/home/raspberry/LIVI/extracted/resources/app.asar', 'rb') as f:
        pass
    # Check version from package.json if accessible
    r = subprocess.run(['cat', '/home/raspberry/LIVI/version'], capture_output=True, text=True, timeout=5)
    print(f'  version file: {r.stdout.strip() or "not found"}')
except:
    pass
# Check from the app directory
r = subprocess.run(['ls', '/home/raspberry/LIVI/'], capture_output=True, text=True, timeout=5)
print(f'  LIVI dir contents: {r.stdout.strip()[:200]}')

print('=== wlan1 capabilities ===')
# Check if wlan1 supports AP mode
try:
    with open('/sys/class/net/wlan1/operstate') as f:
        print(f'  operstate: {f.read().strip()}')
except:
    print('  operstate: N/A')

# Try to bring wlan1 up and check AP support
print('=== Bringing wlan1 up to check capabilities ===')
r = subprocess.run(['sudo', 'ip', 'link', 'set', 'wlan1', 'up'], capture_output=True, text=True, timeout=5)
print(f'  ip link set up: rc={r.returncode}, {r.stderr.strip() or "OK"}')

import time
time.sleep(2)

# Check if it supports AP mode via iw (if installed) or /proc
r = subprocess.run(['iw', 'list'], capture_output=True, text=True, timeout=5)
if r.returncode == 0:
    # Look for AP support
    has_ap = 'AP' in r.stdout
    print(f'  iw list: AP support = {has_ap}')
    # Look for 5GHz support
    has_5ghz = '5180' in r.stdout or '5745' in r.stdout or '5200' in r.stdout
    print(f'  iw list: 5GHz support = {has_5ghz}')
else:
    print(f'  iw list: {r.stderr.strip() or "iw not installed"}')
    # Try nmcli
    r = subprocess.run(['nmcli', 'dev', 'wifi', 'list', 'ifname', 'wlan1'], capture_output=True, text=True, timeout=15)
    print(f'  nmcli scan on wlan1: rc={r.returncode}, {len(r.stdout.split(chr(10)))} lines')
    if r.stdout.strip():
        print(f'  {r.stdout[:300]}')

# Check wlan1 state after bringing up
try:
    with open('/sys/class/net/wlan1/operstate') as f:
        print(f'  wlan1 operstate now: {f.read().strip()}')
except:
    pass

r = subprocess.run(['nmcli', 'dev', 'status'], capture_output=True, text=True, timeout=5)
for line in r.stdout.split('\n'):
    if 'wlan1' in line:
        print(f'  nmcli: {line.strip()}')
