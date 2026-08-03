#!/usr/bin/env python3
"""Thorough BT debug: check pairing state, LIVI auto-connect, stale entries."""
import subprocess, json, os

print('=== 1. BT paired devices (detailed) ===')
r = subprocess.run(['bluetoothctl', 'devices'], capture_output=True, text=True, timeout=5)
print(r.stdout)

for line in r.stdout.strip().split('\n'):
    if line.startswith('Device '):
        mac = line.split()[1]
        print(f'\n--- {mac} ---')
        r2 = subprocess.run(['bluetoothctl', 'info', mac], capture_output=True, text=True, timeout=5)
        print(r2.stdout)

print('=== 2. BT adapter state ===')
r = subprocess.run(['bluetoothctl', 'show'], capture_output=True, text=True, timeout=5)
print(r.stdout)

print('=== 3. LIVI config (BT/AA/wireless related) ===')
try:
    with open('/home/raspberry/.config/LIVI/config.json') as f:
        cfg = json.load(f)
    for k in sorted(cfg.keys()):
        if any(x in k.lower() for x in ['bt', 'blue', 'aa', 'wireless', 'wifi', 'auto', 'conn', 'phone', 'last', 'carname', 'btname']):
            print(f'  {k}: {cfg[k]}')
except Exception as e:
    print(f'  Error: {e}')

print()
print('=== 4. LIVI helper env (wireless AA) ===')
r = subprocess.run(['pgrep', '-f', 'livi-helper'], capture_output=True, text=True, timeout=5)
for pid in r.stdout.strip().split('\n'):
    if not pid:
        continue
    r2 = subprocess.run(['sudo', '-S', 'cat', f'/proc/{pid}/environ'],
                       input='pi\n', capture_output=True, text=True, timeout=5)
    for var in r2.stdout.split('\x00'):
        if 'LIVI' in var and ('WIRELESS' in var or 'AA' in var or 'BT' in var or 'WIFI' in var):
            print(f'  PID {pid}: {var}')

print()
print('=== 5. LIVI helper BT auto-connect targets ===')
# Check if LIVI has stored the phone MAC for auto-connect
r = subprocess.run(['grep', '-r', 'lastConnected\|reconnect\|auto.*conn\|4C:2E', 
                    '/home/raspberry/.config/LIVI/'],
                   capture_output=True, text=True, timeout=10)
print(r.stdout[:500] if r.stdout else '  (no matches)')

# Check config for lastConnectedAaBtMac
print(f'  lastConnectedAaBtMac: {cfg.get("lastConnectedAaBtMac", "(empty)")}')
print(f'  autoConn: {cfg.get("autoConn", "(not set)")}')
print(f'  UseBTPhone: {cfg.get("UseBTPhone", "(not set)")}')

print()
print('=== 6. BlueZ auto-connect behavior ===')
# Check if there's a BlueZ auto-connect plugin or service
r = subprocess.run(['systemctl', '--user', 'list-units', '--type=service', '--state=active'],
                   capture_output=True, text=True, timeout=5)
for line in r.stdout.split('\n'):
    if 'bt' in line.lower() or 'blue' in line.lower() or 'livi' in line.lower():
        print(f'  {line.strip()}')

print()
print('=== 7. Check if Pi is actively trying to connect to phone ===')
# Check rfcomm connections
r = subprocess.run(['rfcomm', '-a'], capture_output=True, text=True, timeout=5)
print(f'  rfcomm: {r.stdout.strip() or "none"}')

# Check active BT connections
r = subprocess.run(['btmgmt', 'info'], capture_output=True, text=True, timeout=5)
print(f'  btmgmt: {r.stdout.strip()}')

# Check if LIVI helper is trying to reconnect
print()
print('=== 8. LIVI helper reconnect logic ===')
helper_path = '/home/raspberry/LIVI/extracted/resources/driver/helper/livi-helper.py'
if os.path.exists(helper_path):
    with open(helper_path) as f:
        lines = f.readlines()
    for i, line in enumerate(lines, 1):
        if any(x in line.lower() for x in ['reconnect', 'auto.*conn', 'lastconnected', 'trusted']):
            print(f'  {i}: {line.rstrip()}')

print()
print('=== 9. Trusted devices ===')
r = subprocess.run(['bluetoothctl', 'devices'], capture_output=True, text=True, timeout=5)
for line in r.stdout.strip().split('\n'):
    if line.startswith('Device '):
        mac = line.split()[1]
        r2 = subprocess.run(['bluetoothctl', 'info', mac], capture_output=True, text=True, timeout=5)
        if 'Trusted: yes' in r2.stdout:
            name = line.split(' ', 2)[2] if len(line.split(' ', 2)) >= 3 else 'unknown'
            print(f'  TRUSTED: {name} ({mac})')
