#!/usr/bin/env python3
"""Find files containing key projection strings in app.asar."""
import struct, json, os

asar_path = '/home/raspberry/LIVI/extracted/resources/app.asar'
out_dir = '/home/raspberry/projection_extracted'
os.makedirs(out_dir, exist_ok=True)

with open(asar_path, 'rb') as f:
    f.seek(0)
    vals = struct.unpack('<IIII', f.read(16))
    json_size = vals[3]
    header_json = f.read(json_size).decode('utf-8')
    data_offset = 16 + json_size
    if data_offset % 4 != 0:
        data_offset = (data_offset + 3) & ~3

header = json.loads(header_json)

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

# Search for key strings in JS files
key_strings = ['aaContentArea', 'videoCrop', 'projectionViewArea', 'applyVideoCrop', 'setContentRegion']
candidates = []

for path, offset, size in files:
    if not path.endswith('.js'):
        continue
    if 'test' in path.lower() or 'node_modules' in path:
        continue
    if size > 10_000_000:  # Skip huge files
        continue
    # Read the file
    with open(asar_path, 'rb') as f:
        f.seek(data_offset + offset)
        data = f.read(size).decode('utf-8', errors='replace')
    
    found = [s for s in key_strings if s in data]
    if found:
        print(f"  {path} ({size} bytes) -> contains: {found}")
        candidates.append((path, offset, size, data, found))

# Save the candidates
for path, offset, size, data, found in candidates:
    outpath = os.path.join(out_dir, path.replace('/', '_'))
    with open(outpath, 'w') as f:
        f.write(data)
    print(f"  Saved {path} -> {outpath}")

print(f"---done, {len(candidates)} files saved---")
