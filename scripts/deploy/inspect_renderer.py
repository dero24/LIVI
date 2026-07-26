#!/usr/bin/env python3
"""Extract out/renderer/index.js from the patched asar and print context
around key markup patterns (logo/status overlay, projection-root styles)."""
import struct, json, re

asar_path = '/home/raspberry/LIVI/extracted/resources/app.asar'

with open(asar_path, 'rb') as f:
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
renderer_js = None
for path, offset, size in files:
    if path == 'out/renderer/index.js':
        with open(asar_path, 'rb') as f:
            f.seek(data_offset + offset)
            renderer_js = f.read(size).decode('utf-8')
        break

if not renderer_js:
    print("ERROR: renderer not found")
    raise SystemExit(1)

print(f"renderer size: {len(renderer_js)}")

# Only inspect the part BEFORE our overlay marker (LIVI's own code)
marker = '// ===== HOME PHONE HUB'
idx = renderer_js.find(marker)
livi_js = renderer_js[:idx] if idx != -1 else renderer_js
print(f"livi code size: {len(livi_js)}")

def show(pattern, label, ctx=220, max_hits=4):
    hits = list(re.finditer(pattern, livi_js))
    print(f"\n##### {label}: {len(hits)} hit(s)")
    for m in hits[:max_hits]:
        s = max(0, m.start() - ctx)
        e = min(len(livi_js), m.end() + ctx)
        print('...' + livi_js[s:e].replace('\n', ' ') + '...')
        print('---')

show(r'role:"status"', 'role=status')
show(r'aria-live', 'aria-live')
show(r'CropPortrait', 'CropPortrait icon')
show(r'projection-root', 'projection-root id', ctx=400, max_hits=2)
show(r'showProjectionOverlay|show-video', 'showProjectionOverlay/show-video', ctx=300, max_hits=4)
