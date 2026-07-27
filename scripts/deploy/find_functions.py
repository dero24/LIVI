#!/usr/bin/env python3
"""Find the Kf and ks functions and the emitMessage path."""
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

    # Find Kf function (buildCpCallCommand)
    # It's used as: this.emit(`message`,Kf(H.AudioAttentionRinging))
    idx = content.find('Kf(H.AudioAttentionRinging)')
    if idx != -1:
        # Find the Kf function definition
        # Search backwards for "function Kf" or "Kf="
        for search in ['function Kf', 'Kf=', 'Kf =']:
            kidx = content.find(search)
            if kidx != -1:
                end = min(len(content), kidx + 400)
                print(f"=== Kf definition at offset {kidx} ===")
                print(content[kidx:end])
                print("---")
                break

    # Find ks function (buildAudioCommandMessage for AA)
    # It's used as: n.emitMessage(ks(e,t))
    idx2 = content.find('ks(e,t)')
    if idx2 != -1:
        for search in ['function ks', 'ks=', 'ks =']:
            kidx2 = content.find(search)
            if kidx2 != -1:
                end2 = min(len(content), kidx2 + 400)
                print(f"\n=== ks definition at offset {kidx2} ===")
                print(content[kidx2:end2])
                print("---")
                break

    # Find the exact PHONE_STATUS handler with more context
    handler_search = 'if(e===Z.PHONE_STATUS){if(n===32769)try{'
    idx3 = content.find(handler_search)
    if idx3 != -1:
        end3 = min(len(content), idx3 + 500)
        print(f"\n=== Exact handler at offset {idx3} ===")
        print(content[idx3:end3])
        print("---")

        # Also show what comes right before (to understand the emit path)
        start3 = max(0, idx3 - 300)
        print(f"\n=== Context before handler ===")
        print(content[start3:idx3])
        print("---")

    # Find how emitMessage works in the AaEventBridge
    # The bridge has: emitMessage: (msg) => this.emit('message', msg)
    # And the session has: this.emit('message', msg) → reaches onDriverMessage
    # Let's find onDriverMessage
    idx4 = content.find('onDriverMessage')
    if idx4 != -1:
        start4 = max(0, idx4 - 100)
        end4 = min(len(content), idx4 + 300)
        print(f"\n=== onDriverMessage at offset {idx4} ===")
        print(content[start4:end4])
        print("---")

    # Find how messages reach the renderer (the IPC bridge)
    # Search for 'audio' event type being sent to renderer
    idx5 = content.find("'audio'")
    if idx5 == -1:
        idx5 = content.find('`audio`')
    if idx5 != -1:
        start5 = max(0, idx5 - 200)
        end5 = min(len(content), idx5 + 200)
        print(f"\n=== 'audio' event at offset {idx5} ===")
        print(content[start5:end5])
        print("---")

    break
