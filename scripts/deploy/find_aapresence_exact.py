#!/usr/bin/env python3
"""Find the exact onAaPresence string to patch."""
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

    # Find onAaPresence
    idx = content.find('onAaPresence(e,t){')
    if idx != -1:
        # Show 600 chars
        end = min(len(content), idx + 600)
        text = content[idx:end]
        print(f"=== onAaPresence at offset {idx} ===")
        print(text)
        print("---")

        # Find the exact ending of the status block
        # Look for "return}" after noteStatus in this region
        ret_idx = text.find('return}')
        if ret_idx != -1:
            print(f"\n'return}}' found at offset {ret_idx} within handler")
            # Show the 100 chars before and after
            start = max(0, ret_idx - 100)
            end2 = min(len(text), ret_idx + 50)
            print(f"\nContext around return}}:")
            print(text[start:end2])
            print("---")

            # Show the exact string we need to match (last 80 chars before return})
            exact_end = text[:ret_idx+7]
            print(f"\nLast 120 chars before and including return}}:")
            print(repr(exact_end[-120:]))
    break
