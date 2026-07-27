#!/usr/bin/env python3
"""Extract the exact PhoneStatus handler code from main.js."""
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

    # Find the PHONE_STATUS handler — it has "32769" (0x8001) near it
    search = 'Z.PHONE_STATUS){if(n===32769)'
    idx = content.find(search)
    if idx == -1:
        # Try alternate patterns
        search = 'PHONE_STATUS){if'
        idx = content.find(search)
    if idx == -1:
        print("Handler not found with exact match, searching broader...")
        # Find all occurrences of PHONE_STATUS
        idx2 = 0
        count = 0
        while True:
            idx2 = content.find('PHONE_STATUS', idx2)
            if idx2 == -1:
                break
            count += 1
            start = max(0, idx2 - 50)
            end = min(len(content), idx2 + 300)
            print(f"\n--- Occurrence {count} at offset {idx2} ---")
            print(content[start:end])
            idx2 += 12
        break

    # Show 600 chars around the handler
    start = max(0, idx - 100)
    end = min(len(content), idx + 600)
    print(f"=== PHONE_STATUS handler at offset {idx} ===")
    print(content[start:end])
    print(f"\n=== End ===")

    # Now find how the renderer receives audio events
    # Search for "AudioAttentionRinging" usage (not definition)
    for term in ['AudioAttentionRinging', 'AttentionRinging']:
        idx3 = 0
        while True:
            idx3 = content.find(term, idx3)
            if idx3 == -1:
                break
            start3 = max(0, idx3 - 200)
            end3 = min(len(content), idx3 + 200)
            print(f"\n--- {term} at offset {idx3} ---")
            print(content[start3:end3])
            idx3 += len(term)

    # Find how audio command messages are emitted in AA path
    # Look for "audio-start" or "audio-stop" events
    for term in ['audio-start', 'audio-stop', 'audioLifecycleCommand']:
        idx4 = content.find(term)
        if idx4 != -1:
            start4 = max(0, idx4 - 200)
            end4 = min(len(content), idx4 + 400)
            print(f"\n--- {term} at offset {idx4} ---")
            print(content[start4:end4])
    break
