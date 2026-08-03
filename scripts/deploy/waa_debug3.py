#!/usr/bin/env python3
"""Check LIVI's wifi_ap module and add LIVI_AA_WIRELESS env var to service."""
import subprocess, os

# Find the wifi_ap module
print('=== Finding wifi_ap module ===')
r = subprocess.run(['find', '/home/raspberry/LIVI/extracted/resources/driver', '-name', 'wifi_ap*'],
                   capture_output=True, text=True, timeout=5)
print(f'  {r.stdout.strip()}')

# Read it
for path in r.stdout.strip().split('\n'):
    if path and os.path.exists(path):
        print(f'\n=== {path} ===')
        with open(path) as f:
            content = f.read()
        # Show key parts
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if any(x in line.lower() for x in ['def ', 'hostapd', 'wlan', 'iface', 'channel', 'ssid', 'password', 'config', 'subprocess', 'popen', 'ip ', 'nmcli', 'rfkill', 'iw ']):
                print(f'  {i}: {line.rstrip()}')

# Check the config module for WIFI_IFACE
print()
print('=== shared/config.py ===')
r = subprocess.run(['find', '/home/raspberry/LIVI/extracted/resources/driver', '-name', 'config.py', '-path', '*/shared/*'],
                   capture_output=True, text=True, timeout=5)
config_path = r.stdout.strip()
if config_path and os.path.exists(config_path):
    with open(config_path) as f:
        for i, line in enumerate(f, 1):
            if any(x in line for x in ['WIFI_IFACE', 'WIFI_', 'BTNAME', 'BT_ADAPTER', 'AA_WIRELESS', 'CP_WIRELESS']):
                print(f'  {i}: {line.rstrip()}')

# Check the current service file
print()
print('=== Current livi.service ===')
service_path = '/home/raspberry/.config/systemd/user/livi.service'
with open(service_path) as f:
    service_content = f.read()
print(service_content)

# Check if LIVI_AA_WIRELESS is already set
has_wireless_env = 'LIVI_AA_WIRELESS' in service_content
print(f'LIVI_AA_WIRELESS in service: {has_wireless_env}')

# Also check if LIVI reads wirelessAaEnabled from config.json
# and sets the env var itself
print()
print('=== Check if LIVI sets LIVI_AA_WIRELESS from config.json ===')
# Search the asar for the connection between wirelessAaEnabled and LIVI_AA_WIRELESS
r = subprocess.run(['strings', '/home/raspberry/LIVI/extracted/resources/app.asar'],
                   capture_output=True, text=True, timeout=10)
for line in r.stdout.split('\n'):
    if 'LIVI_AA_WIRELESS' in line:
        print(f'  asar: {line[:150]}')
