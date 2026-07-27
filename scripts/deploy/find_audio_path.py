#!/usr/bin/env python3
"""Find how AudioData messages reach the renderer."""
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

    # Find onDriverMessage and show more context
    idx = content.find('this.onDriverMessage=e=>{')
    if idx != -1:
        end = min(len(content), idx + 2000)
        print(f"=== onDriverMessage (offset {idx}) ===")
        print(content[idx:end])
        print("---")

    # Find how AudioData is forwarded to renderer
    # Search for "AudioData" in the message handling
    for term in ['instanceof yo', 'AudioData', 'handleAudioData', 'sendAudioEvent']:
        idx2 = content.find(term)
        if idx2 != -1 and idx2 > 500000:  # In the service section, not the enum definition
            start2 = max(0, idx2 - 200)
            end2 = min(len(content), idx2 + 400)
            print(f"\n=== {term} at offset {idx2} ===")
            print(content[start2:end2])
            print("---")

    # Find how events are sent to renderer (webContents.send)
    idx3 = content.find('webContents.send')
    if idx3 != -1:
        start3 = max(0, idx3 - 200)
        end3 = min(len(content), idx3 + 300)
        print(f"\n=== webContents.send at offset {idx3} ===")
        print(content[start3:end3])
        print("---")

    # Find the projection event bridge — how messages go from main to renderer
    idx4 = content.find("'projection-event'")
    if idx4 == -1:
        idx4 = content.find('projection-event')
    if idx4 != -1:
        start4 = max(0, idx4 - 200)
        end4 = min(len(content), idx4 + 300)
        print(f"\n=== projection-event at offset {idx4} ===")
        print(content[start4:end4])
        print("---")

    break
