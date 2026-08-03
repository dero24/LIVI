#!/usr/bin/env python3
"""
Extract the exact compiled bytes around onAaPresence / signalStrength
from LIVI's main.js so we can fix the caller-ID patch regex.
"""
import json, struct, os

ASAR_PATH = '/home/raspberry/LIVI/extracted/resources/app.asar'

with open(ASAR_PATH, 'rb') as f:
    # ASAR header: 4 uint32s (16 bytes), 4th is JSON size
    vals = struct.unpack('<IIII', f.read(16))
    json_size = vals[3]
    header_json = f.read(json_size).decode('utf-8')
    data_offset = 16 + json_size
    if data_offset % 4 != 0:
        data_offset = (data_offset + 3) & ~3

    header = json.loads(header_json)

def find_files(node, path=''):
    result = []
    if 'files' in node:
        for name, child in node['files'].items():
            full = path + '/' + name
            if 'files' in child:
                result.extend(find_files(child, full))
            else:
                result.append((full, child.get('offset'), child.get('size')))
    return result

files = find_files(header)

# Find main.js
main_path = None
main_offset = None
main_size = None
for path, offset, size in files:
    if path.endswith('/main.js') or path == '/main.js':
        main_path = path
        main_offset = int(offset) if offset else 0
        main_size = int(size) if size else 0
        break

if not main_path:
    print('main.js not found in ASAR')
    exit(1)

print(f'Found main.js at {main_path} (offset={main_offset}, size={main_size})')

with open(ASAR_PATH, 'rb') as f:
    f.seek(data_offset + main_offset)
    main_js = f.read(main_size).decode('utf-8', errors='ignore')

print(f'main.js: {len(main_js)} chars')

# Find all signalStrength occurrences and dump context
import re
matches = list(re.finditer(r'signalStrength', main_js))
print(f'\nFound {len(matches)} signalStrength occurrences')

for i, m in enumerate(matches):
    if i >= 5:
        print(f'  ... and {len(matches) - 5} more')
        break
    start = max(0, m.start() - 400)
    end = min(len(main_js), m.end() + 400)
    print(f'\n--- signalStrength context {i} (offset {m.start()}) ---')
    print(main_js[start:end])
    print('---')

# Also search for onAaPresence
aapresence = list(re.finditer(r'onAaPresence', main_js))
print(f'\nFound {len(aapresence)} onAaPresence occurrences')
for i, m in enumerate(aapresence):
    start = max(0, m.start() - 200)
    end = min(len(main_js), m.end() + 500)
    print(f'\n--- onAaPresence context {i} (offset {m.start()}) ---')
    print(main_js[start:end])
    print('---')

# Search for callState
callstate = list(re.finditer(r'callState', main_js))
print(f'\nFound {len(callstate)} callState occurrences')
for i, m in enumerate(callstate):
    start = max(0, m.start() - 200)
    end = min(len(main_js), m.end() + 200)
    print(f'\n--- callState context {i} (offset {m.start()}) ---')
    print(main_js[start:end])
    print('---')
