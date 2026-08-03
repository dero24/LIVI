#!/usr/bin/env python3
"""Inspect LIVI's built-in settings/config UI and WiFi/BT handling."""
import struct, json, re

ASAR = '/home/raspberry/LIVI/extracted/resources/app.asar'

with open(ASAR, 'rb') as f:
    vals = struct.unpack('<IIII', f.read(16))
    header = json.loads(f.read(vals[3]).decode('utf-8'))
    data_offset = 16 + vals[3]
    if data_offset % 4 != 0:
        data_offset = (data_offset + 3) & ~3

def collect(node, path=''):
    result = []
    if 'files' in node:
        for name, child in node['files'].items():
            full = path + '/' + name
            if 'files' in child:
                result.extend(collect(child, full))
            else:
                result.append((full, int(child.get('offset', 0)), int(child.get('size', 0))))
    return result

files = collect(header)

# Find settings/config/wifi related files
print('=== Settings/Config/WiFi/BT files in ASAR ===')
for path, offset, size in files:
    lower = path.lower()
    if any(kw in lower for kw in ['setting', 'wifi', 'bluetooth', 'config', 'connect', 'pair', 'phone']):
        print(f'  {path} ({size} bytes)')

# Find main HTML files
print('\n=== HTML files ===')
for path, offset, size in files:
    if path.endswith('.html') or path.endswith('.htm'):
        print(f'  {path} ({size} bytes)')

# Find the main renderer JS
print('\n=== Main JS files ===')
for path, offset, size in files:
    if path.endswith('.js') and size > 100000:
        print(f'  {path} ({size} bytes)')

# Read the main renderer and search for settings/wifi/bt keywords
print('\n=== Searching renderer for native settings UI ===')
for path, offset, size in files:
    if (path.endswith('.html') or path.endswith('.js')) and size > 50000:
        with open(ASAR, 'rb') as f:
            f.seek(data_offset + offset)
            content = f.read(size).decode('utf-8', errors='ignore')

        # Search for key UI strings
        keywords = ['wirelessAa', 'wirelessCp', 'wifiInterface', 'wifiChannel', 'wifiPassword',
                    'autoConn', 'carName', 'bluetooth', 'pair', 'settings', 'WiFi', 'hotspot',
                    'access point', 'hostapd', 'wlan1', 'btAdapter']
        found = []
        for kw in keywords:
            if kw.lower() in content.lower():
                # Get context
                idx = content.lower().find(kw.lower())
                ctx = content[max(0,idx-40):idx+60].replace('\n',' ')
                found.append(f'    {kw}: ...{ctx}...')
        if found:
            print(f'\n  {path} ({size} bytes):')
            for line in found[:20]:
                print(line)
