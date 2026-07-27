#!/usr/bin/env python3
"""Find the AaEventBridge in compiled main.js to check if callState is forwarded."""
import struct, json

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
    if path != 'out/main/main.js':
        continue
    with open(asar_path, 'rb') as f:
        f.seek(data_offset + offset)
        content = f.read(size).decode('utf-8', errors='ignore')

    # Find emitDeviceStatus in the compiled code
    for term in ['emitDeviceStatus', 'device-status', 'device-presence']:
        idx = 0
        count = 0
        while count < 5:
            idx = content.find(term, idx)
            if idx == -1:
                break
            count += 1
            start = max(0, idx - 100)
            end = min(len(content), idx + 200)
            print(f"\n=== {term} occurrence {count} at offset {idx} ===")
            print(content[start:end])
            print("---")
            idx += len(term)

    break
