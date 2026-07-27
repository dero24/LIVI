#!/usr/bin/env python3
"""Extract renderer JS and check with node --check."""
import struct, json, subprocess

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

for path, offset, size in files:
    if path != 'out/renderer/index.js':
        continue
    with open(asar_path, 'rb') as f:
        f.seek(data_offset + offset)
        content = f.read(size).decode('utf-8', errors='ignore')

    # Write to file
    with open('/tmp/renderer_check.js', 'w') as f:
        f.write(content)
    print(f"Wrote {len(content)} chars to /tmp/renderer_check.js")

    # Check with node
    result = subprocess.run(['node', '--check', '/tmp/renderer_check.js'],
                          capture_output=True, text=True, timeout=30)
    if result.returncode == 0:
        print("node --check: PASSED")
    else:
        print(f"node --check: FAILED")
        print(f"stderr: {result.stderr[:2000]}")
    break
