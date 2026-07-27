#!/usr/bin/env python3
"""Search for LIVI's media control button handlers."""
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

content = extract_file('out/renderer/index.js')
text = content.decode('utf-8', errors='ignore')

# Find Yx function and its callers
idx = text.find('Yx=')
if idx >= 0:
    start = max(0, idx - 50)
    end = min(len(text), idx + 300)
    print(f"=== Yx definition at pos {idx} ===")
    print(text[start:end])
    print("---")

# Search for Yx( calls
import re
for m in re.finditer(r'Yx\(`[^`]+`\)', text):
    idx = m.start()
    start = max(0, idx - 100)
    end = min(len(text), idx + 100)
    print(f"\n=== Yx call at pos {idx} ===")
    print(text[start:end])
    print("---")

# Also search for the V enum to find play/pause/next/prev values
content2 = extract_file('out/main/main.js')
text2 = content2.decode('utf-8', errors='ignore')

# Get the full V enum
idx = text2.find('var V=function')
if idx >= 0:
    end = text2.find('}(', idx)
    if end < 0:
        end = idx + 2000
    print(f"\n=== V enum at pos {idx} ===")
    print(text2[idx:min(end+10, idx+2000)])
    print("---")
