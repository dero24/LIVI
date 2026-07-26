#!/usr/bin/env python3
"""Test WiFi parsing."""
import subprocess

r = subprocess.run(['nmcli', '-t', '-f', 'IN-USE,SIGNAL,SECURITY,FREQ,SSID', 'dev', 'wifi', 'list'],
                   capture_output=True, text=True, timeout=15)
print("RAW OUTPUT:")
print(repr(r.stdout))
print("\nPARSED:")
for line in r.stdout.strip().split('\n'):
    if not line:
        continue
    in_use = line.startswith('*')
    if len(line) > 1 and line[1] == ':':
        line = line[2:]
    else:
        line = line[1:] if line else ''
    parts = line.split(':', 3)
    if len(parts) < 4:
        print(f"  SKIP (only {len(parts)} parts): {parts}")
        continue
    signal = int(parts[0]) if parts[0].isdigit() else 0
    security = parts[1] if parts[1] else 'Open'
    freq = parts[2]
    ssid = parts[3]
    if not ssid:
        print(f"  SKIP (empty ssid): signal={signal}")
        continue
    print(f"  ssid={ssid} signal={signal} security={security} freq={freq} in_use={in_use}")
