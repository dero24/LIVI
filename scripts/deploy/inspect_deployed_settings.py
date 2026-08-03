#!/usr/bin/env python3
"""Extract the deployed HomeHub overlay from LIVI's ASAR and inspect the settings UI."""
import struct, json, re, sys

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
renderer = None
for path, offset, size in files:
    if path == '/out/renderer/index.js':
        with open(ASAR, 'rb') as f:
            f.seek(data_offset + offset)
            renderer = f.read(size).decode('utf-8', errors='ignore')
        break

if not renderer:
    print('renderer not found'); sys.exit(1)

# Find the HomeHub overlay section
idx = renderer.find('// ===== HOME PHONE HUB')
if idx == -1:
    print('HomeHub overlay NOT FOUND in deployed ASAR')
    sys.exit(1)

overlay = renderer[idx:]
print(f'=== DEPLOYED OVERLAY: {len(overlay)} chars ===\n')

# 1. Settings overlay function - dump it fully
m = re.search(r'function homehubOpenSettings\(\)\s*\{', overlay)
if m:
    start = m.start()
    # Find matching close brace
    depth = 0
    i = overlay.index('{', start)
    for j in range(i, min(i + 20000, len(overlay))):
        if overlay[j] == '{': depth += 1
        elif overlay[j] == '}':
            depth -= 1
            if depth == 0:
                print('=== homehubOpenSettings() (DEPLOYED) ===')
                print(overlay[start:j+1])
                break
else:
    print('homehubOpenSettings NOT FOUND')

print('\n\n=== ALL BUTTONS IN SETTINGS TOP BAR ===')
# Find textContent assignments near settings
for m in re.finditer(r'(\w+)\.textContent\s*=\s*[\'"`]([^\'"`]+)[\'"`]', overlay):
    var, txt = m.group(1), m.group(2)
    if any(k in var.lower() for k in ['btn', 'title', 'label']):
        print(f'  {var}.textContent = "{txt}"')
