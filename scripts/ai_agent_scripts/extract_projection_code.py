#!/usr/bin/env python3
"""Extract minified Projection files from app.asar using raw parsing."""
import struct, json, os

asar_path = '/home/raspberry/LIVI/extracted/resources/app.asar'
out_dir = '/home/raspberry/projection_extracted'
os.makedirs(out_dir, exist_ok=True)

with open(asar_path, 'rb') as f:
    # Read first 16 bytes
    f.seek(0)
    vals = struct.unpack('<IIII', f.read(16))
    print(f"Header values: {vals}")
    # vals = (4, 10721260, 10721256, 10721251)
    # The JSON starts at byte 16, with size vals[3]
    json_size = vals[3]
    header_json = f.read(json_size).decode('utf-8')
    print(f"JSON starts with: {header_json[:80]}")
    print(f"JSON ends with: {header_json[-80:]}")
    
    # Data offset = 16 + json_size, padded to 4-byte alignment
    data_offset = 16 + json_size
    if data_offset % 4 != 0:
        data_offset = (data_offset + 3) & ~3
    print(f"Data offset: {data_offset}")

header = json.loads(header_json)
print(f"Header parsed OK, top keys: {list(header.keys())}")

# Recursively find all files
def find_files(node, prefix=''):
    results = []
    if 'files' in node:
        for name, child in node['files'].items():
            path = f"{prefix}/{name}" if prefix else name
            if 'files' in child:
                results.extend(find_files(child, path))
            elif 'offset' in child:
                results.append((path, int(child['offset']), child.get('size', 0)))
    return results

files = find_files(header)
print(f"Total files: {len(files)}")

# Find our targets
targets = ['ProjectionService', 'androidAuto', 'Projection.js']
for path, offset, size in files:
    if any(t in path for t in targets) and 'test' not in path.lower() and path.endswith('.js'):
        f_pos = data_offset + offset
        with open(asar_path, 'rb') as f:
            f.seek(f_pos)
            data = f.read(size).decode('utf-8', errors='replace')
        outpath = os.path.join(out_dir, path.replace('/', '_'))
        with open(outpath, 'w') as f:
            f.write(data)
        print(f"Extracted {path} -> {len(data)} chars")

print("done")
