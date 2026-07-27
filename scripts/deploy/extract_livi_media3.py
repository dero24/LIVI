#!/usr/bin/env python3
"""Search LIVI's main.js for sendCommand and media command handling."""
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

# Search for the V enum (command types) and sendCommand IPC
for keyword in ['sendCommand', '_sendCommand', 'V.play', 'V.pause', 'V.playPause', 'V.next', 'V.prev', 'sendMedia', 'Ku.play', 'Ku.pause', 'Ku.playPause', 'Ku.next', 'Ku.prev']:
    idx = 0
    count = 0
    while count < 2:
        idx = text.find(keyword, idx)
        if idx < 0:
            break
        start = max(0, idx - 100)
        end = min(len(text), idx + 200)
        print(f"\n=== '{keyword}' at pos {idx} ===")
        print(text[start:end])
        print("---")
        idx += len(keyword)
        count += 1

# Search for the V enum definition
for pattern in ['V={', 'V =', 'play:', 'pause:', 'playPause:', 'next:', 'prev:']:
    idx = text.find(pattern)
    if idx >= 0 and 'KeyP' not in text[idx:idx+100]:  # Skip the keymap
        start = max(0, idx - 50)
        end = min(len(text), idx + 200)
        print(f"\n=== enum pattern '{pattern}' at pos {idx} ===")
        print(text[start:end])
        print("---")

# Search for how sendCommand is exposed to renderer (IPC bridge)
for keyword in ['ipc.sendCommand', 'sendCommand=', 'sendCommand:', '"sendCommand"', "'sendCommand'"]:
    idx = 0
    count = 0
    while count < 2:
        idx = text.find(keyword, idx)
        if idx < 0:
            break
        start = max(0, idx - 100)
        end = min(len(text), idx + 200)
        print(f"\n=== IPC '{keyword}' at pos {idx} ===")
        print(text[start:end])
        print("---")
        idx += len(keyword)
        count += 1
