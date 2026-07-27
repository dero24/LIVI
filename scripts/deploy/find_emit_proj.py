#!/usr/bin/env python3
"""Find emitProjectionEvent in the compiled main.js."""
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

    # Find emitProjectionEvent
    idx = content.find('emitProjectionEvent')
    count = 0
    while idx != -1 and count < 5:
        start = max(0, idx - 100)
        end = min(len(content), idx + 300)
        print(f"\n=== emitProjectionEvent occurrence {count+1} at offset {idx} ===")
        print(content[start:end])
        print("---")
        idx = content.find('emitProjectionEvent', idx + 1)
        count += 1

    # Also find the call event we patched
    call_idx = content.find("type:`call`")
    if call_idx == -1:
        call_idx = content.find("type:'call'")
    if call_idx != -1:
        start = max(0, call_idx - 200)
        end = min(len(content), call_idx + 200)
        print(f"\n=== type:call event at offset {call_idx} ===")
        print(content[start:end])
    else:
        print("\ntype:call event NOT FOUND in main.js!")

    # Check if the onAaPresence patch is there
    aapatch = content.find("if(t.callState){this.emitProjectionEvent")
    if aapatch != -1:
        start = max(0, aapatch - 100)
        end = min(len(content), aapatch + 200)
        print(f"\n=== onAaPresence call patch at offset {aapatch} ===")
        print(content[start:end])
    else:
        print("\nonAaPresence call patch NOT FOUND!")

    break
