#!/usr/bin/env python3
"""Probe dongle details (iw not installed, use nmcli + /sys)."""
import subprocess, os, glob

print('=== wlan1 interface details ===')
# /sys/class/net/wlan1
for attr in ['address', 'mtu', 'operstate', 'tx_queues']:
    path = f'/sys/class/net/wlan1/{attr}'
    try:
        with open(path) as f:
            print(f'  {attr}: {f.read().strip()}')
    except:
        print(f'  {attr}: N/A')

print()
print('=== Driver info for wlan1 ===')
try:
    link = os.readlink('/sys/class/net/wlan1/device/driver')
    print(f'  driver: {link}')
except:
    print('  driver: unknown')
try:
    with open('/sys/class/net/wlan1/device/uevent') as f:
        print(f'  uevent: {f.read().strip()}')
except:
    print('  uevent: N/A')

print()
print('=== nmcli device status ===')
r = subprocess.run(['nmcli', 'dev', 'status'], capture_output=True, text=True, timeout=5)
print(r.stdout)

print('=== nmcli connections ===')
r = subprocess.run(['nmcli', '-t', '-f', 'NAME,DEVICE,TYPE,STATE', 'con', 'show'], capture_output=True, text=True, timeout=5)
print(r.stdout)

print('=== Can wlan1 scan? ===')
r = subprocess.run(['nmcli', 'dev', 'wifi', 'list', 'ifname', 'wlan1'], capture_output=True, text=True, timeout=15)
if r.returncode == 0:
    lines = r.stdout.strip().split('\n')
    print(f'  Scan returned {len(lines)-1} networks')
    for line in lines[:5]:
        print(f'  {line}')
else:
    print(f'  Scan failed: {r.stderr.strip() or r.stdout.strip()}')

print()
print('=== rfkill status ===')
r = subprocess.run(['rfkill', 'list'], capture_output=True, text=True, timeout=5)
print(r.stdout if r.stdout else '  (no rfkill)')

print()
print('=== hostapd installed? ===')
r = subprocess.run(['which', 'hostapd'], capture_output=True, text=True, timeout=5)
print(f'  hostapd: {r.stdout.strip() or "not installed"}')

print('=== dnsmasq installed? ===')
r = subprocess.run(['which', 'dnsmasq'], capture_output=True, text=True, timeout=5)
print(f'  dnsmasq: {r.stdout.strip() or "not installed"}')

print('=== LIVI wireless AA config ===')
try:
    import json
    with open('/home/raspberry/.config/LIVI/config.json') as f:
        cfg = json.load(f)
    for k in sorted(cfg.keys()):
        if any(x in k.lower() for x in ['wifi', 'wireless', 'aa', 'hotspot', 'ap', 'ssid']):
            print(f'  {k}: {cfg[k]}')
    print(f'  (total config keys: {len(cfg)})')
except Exception as e:
    print(f'  Error: {e}')
