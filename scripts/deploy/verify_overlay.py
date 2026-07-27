#!/usr/bin/env python3
"""Verify our overlay is in the deployed asar."""
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

result = find_file(header, 'out/renderer/index.js')
if result:
    offset, size = result
    header_total = 8 + ((header_size + 7) // 8) * 8
    with open(asar_path, 'rb') as f:
        f.seek(header_total + offset)
        content = f.read(size).decode('utf-8', errors='ignore')

    print('HOME PHONE HUB marker:', 'HOME PHONE HUB' in content)
    print('window.sendCmd:', 'window.sendCmd' in content)
    print('updateNowPlayingFromMedia:', 'updateNowPlayingFromMedia' in content)
    print('sendCmd function count:', content.count('function sendCmd'))
    print('media event handler:', "type === 'media'" in content)
    print('media-reset handler:', "type === 'media-reset'" in content)
    # Check for dead branches
    print('media-metadata (dead):', "type === 'media-metadata'" in content)
    print('media-status (dead):', "type === 'media-status'" in content)
else:
    print('File not found')
