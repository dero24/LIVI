#!/usr/bin/env python3
"""List files in LIVI's app.asar that are media/home/bar related."""
import struct, json

asar_path = '/home/raspberry/LIVI/extracted/resources/app.asar'
with open(asar_path, 'rb') as f:
    f.read(4)  # 0x04000000
    header_size = struct.unpack('<I', f.read(4))[0]
    f.read(8)  # padding
    header_json = f.read(header_size - 8).decode('utf-8', errors='ignore').rstrip('\x00')

header = json.loads(header_json)

def find_files(obj, path=''):
    results = []
    if 'files' in obj:
        for name, info in obj['files'].items():
            full = path + '/' + name if path else name
            if 'files' in info:
                results.extend(find_files(info, full))
            else:
                results.append(full)
    return results

files = find_files(header)
keywords = ['media', 'music', 'now', 'play', 'home', 'bottom', 'bar', 'control', 'dashboard', 'projection', 'ipc']
for f_name in sorted(files):
    lower = f_name.lower()
    if any(k in lower for k in keywords):
        print(f_name)
