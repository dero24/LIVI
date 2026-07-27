#!/usr/bin/env python3
"""Extract the PhoneStatus handling code from main.js to see what we need to patch."""
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

    # Find the PHONE_STATUS handling block
    idx = content.find('Z.PHONE_STATUS')
    if idx == -1:
        print("PHONE_STATUS not found!")
        break

    # Show a wider context (500 chars before and 800 after)
    start = max(0, idx - 300)
    end = min(len(content), idx + 800)
    snippet = content[start:end]

    print(f"=== PHONE_STATUS handling (offset {idx}) ===")
    print(snippet)
    print(f"\n=== End ===")

    # Also find AudioAttentionRinging to see if it's used anywhere
    for term in ['AudioAttentionRinging', 'AttentionRinging', '14']:
        # Search for AudioAttentionRinging specifically
        pass

    ring_idx = content.find('AudioAttentionRinging')
    if ring_idx != -1:
        start2 = max(0, ring_idx - 200)
        end2 = min(len(content), ring_idx + 400)
        print(f"\n=== AudioAttentionRinging found at offset {ring_idx} ===")
        print(content[start2:end2])
    else:
        print("\nAudioAttentionRinging NOT found in main.js")

    # Find how CarPlay emits call commands
    call_idx = content.find('AudioAttentionRinging')
    if call_idx == -1:
        # Search for the numeric value
        call_idx = content.find('buildCpCallCommand')
        if call_idx != -1:
            start3 = max(0, call_idx - 200)
            end3 = min(len(content), call_idx + 400)
            print(f"\n=== buildCpCallCommand at offset {call_idx} ===")
            print(content[start3:end3])

    # Find how audio command messages are built for AA
    audio_cmd_idx = content.find('buildAudioCommandMessage')
    if audio_cmd_idx != -1:
        start4 = max(0, audio_cmd_idx - 100)
        end4 = min(len(content), audio_cmd_idx + 300)
        print(f"\n=== buildAudioCommandMessage at offset {audio_cmd_idx} ===")
        print(content[start4:end4])
    break
