#!/usr/bin/env python3
"""Extract LIVI's renderer JS and search for media event handling."""
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

# Search for media event types in renderer
content = extract_file('out/renderer/index.js')
text = content.decode('utf-8', errors='ignore')

# Find all media-related event types
for keyword in ['media-reset', 'media-metadata', 'MediaPlayStatus', 'MediaSongPlayTime', 'mediaPayloadError', 'media-update', 'media-info', 'playbackStatus']:
    idx = 0
    count = 0
    while count < 3:
        idx = text.find(keyword, idx)
        if idx < 0:
            break
        start = max(0, idx - 150)
        end = min(len(text), idx + 250)
        print(f"\n=== '{keyword}' at pos {idx} ===")
        print(text[start:end])
        print("---")
        idx += len(keyword)
        count += 1

# Also check main.js for media event emission
content2 = extract_file('out/main/main.js')
text2 = content2.decode('utf-8', errors='ignore')

for keyword in ['media-metadata', 'media-reset', 'media-update', 'media-info', 'MediaPlayStatus', 'playbackStatus', 'emitMedia', 'media-status']:
    idx = 0
    count = 0
    while count < 2:
        idx = text2.find(keyword, idx)
        if idx < 0:
            break
        start = max(0, idx - 150)
        end = min(len(text2), idx + 250)
        print(f"\n=== main.js: '{keyword}' at pos {idx} ===")
        print(text2[start:end])
        print("---")
        idx += len(keyword)
        count += 1
