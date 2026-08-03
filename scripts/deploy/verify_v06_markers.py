#!/usr/bin/env python3
"""Verify v0.6 night mode markers in deployed ASAR."""
import json, struct

asar = '/home/raspberry/LIVI/extracted/resources/app.asar'
with open(asar, 'rb') as f:
    vals = struct.unpack('<IIII', f.read(16))
    json_size = vals[3]
    header_json = f.read(json_size).decode('utf-8')
    data_offset = 16 + json_size
    if data_offset % 4 != 0:
        data_offset = (data_offset + 3) & ~3
    header = json.loads(header_json)

    def collect_files(node, prefix=''):
        results = []
        if 'files' in node:
            for name, child in node['files'].items():
                path = f"{prefix}/{name}" if prefix else name
                if 'files' in child:
                    results.extend(collect_files(child, path))
                elif 'offset' in child:
                    results.append((path, int(child['offset']), child.get('size', 0)))
        return results

    files = collect_files(header)
    target = None
    for path, off, sz in files:
        if path == 'out/renderer/index.js':
            target = (off, sz)
            break
    if not target:
        print('ERROR: out/renderer/index.js not found')
        exit(1)
    off, sz = target
    f.seek(data_offset + off)
    content = f.read(sz).decode()

markers = ['homehub-night-dim', 'pollNightMode', 'applyNightMode', 'nightModeActive', 'nightModeConfig']
for m in markers:
    count = content.count(m)
    status = 'OK' if count > 0 else 'MISSING'
    print(f'{status:8} {m}: {count} occurrences')
