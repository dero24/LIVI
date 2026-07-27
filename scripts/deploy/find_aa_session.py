#!/usr/bin/env python3
"""Find the compiled AA Session code in the asar and search for PhoneStatus handling."""
import json
import sys

ASAR_PATH = '/home/raspberry/LIVI/extracted/resources/app.asar'

# Read asar header
with open(ASAR_PATH, 'rb') as f:
    # asar header: 4 bytes pickle size, then JSON header
    f.read(4)  # header size uint32
    header_size_str = f.read(4)
    import struct
    header_size = struct.unpack('<I', header_size_str)[0]
    # Actually asar format: 4 bytes (always 4), 4 bytes header length, then header JSON
    # Let me re-read properly
    f.seek(0)
    raw = f.read(16)
    # The format is: uint32(4) + uint32(header_size) + uint32(0) + uint32(0) then JSON
    # Actually it's: 4 bytes (size of next field), 4 bytes (header size), then header
    f.seek(0)
    # Read 8 bytes
    first_two = f.read(8)
    # First 4 bytes = 4 (size of the next 4 bytes)
    # Next 4 bytes = header size
    import struct
    hdr_sz = struct.unpack('<I', first_two[4:8])[0]
    header_json = f.read(hdr_sz).decode('utf-8').rstrip('\x00')
    header = json.loads(header_json)

# Find all .js files in the asar
def find_js_files(node, path=''):
    results = []
    if 'files' in node:
        for name, child in node['files'].items():
            child_path = path + '/' + name if path else name
            if 'files' in child:
                # It's a directory
                results.extend(find_js_files(child, child_path))
            elif name.endswith('.js'):
                # It's a JS file
                results.append((child_path, child.get('offset', 0), child.get('size', 0)))
    return results

js_files = find_js_files(header)
print(f"Found {len(js_files)} JS files in asar")

# Search for files that might contain the AA session code
# Look for files with "session" or "aa" or "projection" in the path
candidates = [(p, o, s) for p, o, s in js_files if any(x in p.lower() for x in ['session', 'aasession', 'aa/', 'projection/driver'])]
print(f"\nCandidate files ({len(candidates)}):")
for p, o, s in candidates:
    print(f"  {p} ({s} bytes)")

# Also look for the main bundle
main_candidates = [(p, o, s) for p, o, s in js_files if 'main' in p.lower() and s > 100000]
print(f"\nLarge main files ({len(main_candidates)}):")
for p, o, s in main_candidates:
    print(f"  {p} ({s} bytes)")
