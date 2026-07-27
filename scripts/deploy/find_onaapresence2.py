#!/usr/bin/env python3
"""Get full context around onAaPresence handler."""
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

    # Find the AA onAaPresence (occurrence 2 at offset 517649)
    idx = content.find('onAaPresence(e,t){let n=typeof t.ip')
    if idx != -1:
        # Show 800 chars from the start
        end = min(len(content), idx + 800)
        print(f"=== onAaPresence at offset {idx} ===")
        print(content[idx:end])
        print("---")

    # Also find handleAudioData to see how projection-event is sent
    idx2 = content.find('handleAudioData')
    if idx2 != -1:
        # Search forward for 'projection-event' near handleAudioData
        search_region = content[idx2:idx2+3000]
        pe_idx = search_region.find('projection-event')
        if pe_idx != -1:
            abs_idx = idx2 + pe_idx
            start = max(0, abs_idx - 200)
            end = min(len(content), abs_idx + 200)
            print(f"\n=== projection-event in handleAudioData at offset {abs_idx} ===")
            print(content[start:end])
            print("---")
        else:
            # Search for webContents.send in handleAudioData
            wc_idx = search_region.find('webContents')
            if wc_idx != -1:
                abs_idx2 = idx2 + wc_idx
                start2 = max(0, abs_idx2 - 200)
                end2 = min(len(content), abs_idx2 + 200)
                print(f"\n=== webContents in handleAudioData at offset {abs_idx2} ===")
                print(content[start2:end2])
                print("---")

    # Find how audio command events are sent to renderer
    # Search for type:`audio` near handleAudioData
    idx3 = content.find('type:`audio`')
    if idx3 == -1:
        idx3 = content.find("type:'audio'")
    if idx3 != -1:
        start3 = max(0, idx3 - 200)
        end3 = min(len(content), idx3 + 200)
        print(f"\n=== type:'audio' at offset {idx3} ===")
        print(content[start3:end3])
        print("---")

    break
