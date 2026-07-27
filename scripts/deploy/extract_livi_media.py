#!/usr/bin/env python3
"""Extract LIVI's renderer JS and search for readMedia/media handling."""
import struct, json, os

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
                offset = info.get('offset', 0)
                size = info.get('size', 0)
                return int(offset), int(size)
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
    # ASAR header is aligned to 8 bytes, plus 16 bytes for the header framing
    # Actual data starts at: 8 + header_size_padded
    header_total = 8 + ((header_size + 7) // 8) * 8
    with open(asar_path, 'rb') as f:
        f.seek(header_total + offset)
        return f.read(size)

# Search renderer files for readMedia
import re
files_to_check = [
    'out/renderer/assets/index.js',
    'out/renderer/assets/Projection.worker-CjPypAXg.js',
]

# First, find all renderer JS files
def find_all_files(obj, path='', ext='.js'):
    results = []
    if 'files' in obj:
        for name, info in obj['files'].items():
            full = path + '/' + name if path else name
            if 'files' in info:
                results.extend(find_all_files(info, full, ext))
            elif full.endswith(ext):
                results.append(full)
    return results

all_js = find_all_files(header)
renderer_js = [f for f in all_js if 'renderer' in f and ('index' in f or 'Projection' in f or 'main' in f)]
print("Renderer JS files:", renderer_js)

for filepath in renderer_js:
    content = extract_file(filepath)
    if not content:
        continue
    text = content.decode('utf-8', errors='ignore')
    # Search for readMedia, MediaSongName, nowplaying, now-playing, media info
    for keyword in ['readMedia', 'MediaSongName', 'MediaArtistName', 'MediaAPPName', 'nowplaying', 'now-playing', 'NowPlaying', 'mediaInfo', 'MediaInfo', 'playbackStatus', 'MediaPlaybackMetadata']:
        idx = text.find(keyword)
        if idx >= 0:
            start = max(0, idx - 100)
            end = min(len(text), idx + 200)
            print(f"\n=== {filepath} contains '{keyword}' at pos {idx} ===")
            print(text[start:end])
            print("---")

# Also check main process files
main_js = [f for f in all_js if 'main' in f and f.endswith('.js') and 'node_modules' not in f]
print("\n\nMain JS files:", main_js[:10])
for filepath in main_js[:5]:
    content = extract_file(filepath)
    if not content:
        continue
    text = content.decode('utf-8', errors='ignore')
    for keyword in ['readMedia', 'MediaSongName', 'sendCommand', 'playPause', 'mediaInfo']:
        idx = text.find(keyword)
        if idx >= 0:
            start = max(0, idx - 100)
            end = min(len(text), idx + 200)
            print(f"\n=== {filepath} contains '{keyword}' at pos {idx} ===")
            print(text[start:end])
            print("---")
