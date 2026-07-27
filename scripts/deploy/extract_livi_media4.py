#!/usr/bin/env python3
"""Search for V enum definition and sendCommand IPC bridge."""
import struct, json

asar_path = '/home/raspberry/LIVI/extracted/resources/app.asar'
with open(asar_path, 'rb') as f:
    f.read(4)
    header_size = struct.unpack('<I', f.read(4))[0]
    f.read(8)
    header_json = f.read(header_size - 8).decode('utf-8', errors='ignore').rstrip('\x00')

header = json.loads(header_json)

def find_file(obj, target, path=''):
    if 'files' in obj:
        for name, info in obj['files'].items():
            full = path + '/' + name if path else name
            if full == target:
                return int(info.get('offset', 0)), int(info.get('size', 0))
            if 'files' in info:
                result = find_file(info, target, full)
                if result:
                    return result
    return None

def extract_file(filepath):
    result = find_file(header, filepath)
    if not result:
        return None
    offset, size = result
    header_total = 8 + ((header_size + 7) // 8) * 8
    with open(asar_path, 'rb') as f:
        f.seek(header_total + offset)
        return f.read(size)

content = extract_file('out/main/main.js')
text = content.decode('utf-8', errors='ignore')

# Find V enum definition
for pattern in ['V=Object.freeze', 'V ={', 'V={', 'var V=', 'let V=', 'const V=']:
    idx = text.find(pattern)
    if idx >= 0:
        start = max(0, idx - 50)
        end = min(len(text), idx + 400)
        print(f"\n=== '{pattern}' at pos {idx} ===")
        print(text[start:end])
        print("---")

# Find Wo class
for pattern in ['class Wo', 'Wo=', 'new Wo']:
    idx = 0
    count = 0
    while count < 3:
        idx = text.find(pattern, idx)
        if idx < 0:
            break
        start = max(0, idx - 80)
        end = min(len(text), idx + 200)
        print(f"\n=== Wo: '{pattern}' at pos {idx} ===")
        print(text[start:end])
        print("---")
        idx += len(pattern)
        count += 1

# Search renderer for sendCommand IPC
content2 = extract_file('out/renderer/index.js')
text2 = content2.decode('utf-8', errors='ignore')

for keyword in ['sendCommand']:
    idx = 0
    count = 0
    while count < 5:
        idx = text2.find(keyword, idx)
        if idx < 0:
            break
        start = max(0, idx - 150)
        end = min(len(text2), idx + 200)
        print(f"\n=== renderer: '{keyword}' at pos {idx} ===")
        print(text2[start:end])
        print("---")
        idx += len(keyword)
        count += 1
