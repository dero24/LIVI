#!/usr/bin/env python3
"""Find PhoneStatus handling in the compiled asar main process JS."""
import struct, json, os, sys

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
print(f"Total files in asar: {len(files)}")

# Search all JS files for PhoneStatus
for path, offset, size in files:
    if not path.endswith('.js'):
        continue
    if size < 1000:
        continue
    with open(asar_path, 'rb') as f:
        f.seek(data_offset + offset)
        content = f.read(size).decode('utf-8', errors='ignore')
    if 'PhoneStatus' in content or 'phoneStatus' in content or 'phone_status' in content:
        print(f"\n=== Found in {path} ({size} bytes) ===")
        # Find all occurrences and show context
        for search_term in ['PhoneStatus', 'phoneStatus', 'phone_status']:
            idx = 0
            while True:
                idx = content.find(search_term, idx)
                if idx == -1:
                    break
                start = max(0, idx - 200)
                end = min(len(content), idx + 400)
                snippet = content[start:end]
                print(f"\n  [{search_term} at offset {idx}]")
                print(f"  ...{snippet}...")
                print("  ---")
                idx += len(search_term)
