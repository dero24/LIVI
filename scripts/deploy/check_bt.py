#!/usr/bin/env python3
"""Check BT connection state and AA service registration."""
import subprocess

# Check BT paired devices
print('=== Paired BT devices ===')
r = subprocess.run(['bt-device', '--list'], capture_output=True, text=True, timeout=5)
print(r.stdout if r.stdout else '  (bt-device not available)')

# Try bluetoothctl
print('=== bluetoothctl paired devices ===')
r = subprocess.run(['bluetoothctl', 'devices'], capture_output=True, text=True, timeout=5)
print(r.stdout)

# Check connected devices
print('=== Connected BT devices ===')
r = subprocess.run(['bluetoothctl', 'info'], capture_output=True, text=True, timeout=5)
print(r.stdout)

# Check BT services registered (SDP records for AA)
print('=== BT SDP services (looking for AA) ===')
r = subprocess.run(['sdptool', 'browse', 'local'], capture_output=True, text=True, timeout=5)
if r.stdout:
    for line in r.stdout.split('\n'):
        if 'Android Auto' in line or 'AA' in line or 'android' in line.lower() or 'Service Name' in line:
            print(f'  {line}')
else:
    print(f'  sdptool not available or no output: {r.stderr.strip()[:100]}')

# Check rfcomm/listening services
print()
print('=== Listening services ===')
r = subprocess.run(['rfcomm', '-a'], capture_output=True, text=True, timeout=5)
print(r.stdout if r.stdout else '  (no rfcomm connections)')

# Check LIVI helper — is it watching for BT connections?
print('=== LIVI helper BT state ===')
r = subprocess.run(['pgrep', '-a', '-f', 'livi-helper'], capture_output=True, text=True, timeout=5)
print(r.stdout)

# Check if there are any BT-related log messages
print()
print('=== Recent BT-related journal ===')
r = subprocess.run(['journalctl', '--user', '-n', '50', '--no-pager', '-o', 'cat'],
                   capture_output=True, text=True, timeout=5)
for line in r.stdout.split('\n'):
    if any(x in line.lower() for x in ['bt', 'bluetooth', 'pair', 'connect', 'aa', 'wireless', 'rfcomm']):
        print(f'  {line}')

# Check BlueZ logs
print()
print('=== BlueZ journal ===')
r = subprocess.run(['journalctl', '-u', 'bluetooth', '-n', '20', '--no-pager', '-o', 'cat'],
                   capture_output=True, text=True, timeout=5)
for line in r.stdout.split('\n'):
    print(f'  {line}')
