#!/usr/bin/env python3
"""Extract out/main/main.js from the ASAR and dump context around
onAaPresence / signalStrength / batteryLevel / emitProjectionEvent so we can
see the exact compiled shape and fix the caller-ID patch pattern."""
import struct, json, re, sys

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
main_js = None
for path, offset, size in files:
    if path == 'out/main/main.js':
        with open(asar_path, 'rb') as f:
            f.seek(data_offset + offset)
            main_js = f.read(size).decode('utf-8')
        break

if not main_js:
    print('ERROR: main.js not found')
    sys.exit(1)

print(f'main.js: {len(main_js)} chars')

def dump(label, needle, before=200, after=500, max_hits=3):
    print(f'\n===== {label} ({needle!r}) =====')
    hits = [m.start() for m in re.finditer(re.escape(needle), main_js)]
    print(f'{len(hits)} occurrence(s)')
    for h in hits[:max_hits]:
        print(f'--- @{h} ---')
        print(main_js[max(0, h - before):h + after])
        print()

dump('onAaPresence', 'onAaPresence', 100, 900)
dump('signalStrength', 'signalStrength', 400, 300)
dump('batteryLevel', 'batteryLevel', 300, 300, 2)
dump('emitProjectionEvent', 'emitProjectionEvent', 150, 250, 3)
dump('callState', 'callState', 300, 300, 5)
dump('device-presence', 'device-presence', 200, 400, 3)
