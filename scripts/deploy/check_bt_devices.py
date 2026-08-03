#!/usr/bin/env python3
"""Check BT device details to distinguish phones from audio devices."""
import subprocess

r = subprocess.run(['bluetoothctl', 'devices'], capture_output=True, text=True, timeout=5)
print('=== All paired devices ===')
print(r.stdout)

for line in r.stdout.strip().split('\n'):
    if line.startswith('Device '):
        mac = line.split()[1]
        print(f'\n=== {mac} ===')
        r2 = subprocess.run(['bluetoothctl', 'info', mac], capture_output=True, text=True, timeout=5)
        print(r2.stdout)
