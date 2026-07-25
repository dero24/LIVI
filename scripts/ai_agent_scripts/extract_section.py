#!/usr/bin/env python3
"""Extract context around touch handlers and DEBUG flag in app.asar main.js."""
import json, struct

asar_path = '/home/raspberry/LIVI/extracted/resources/app.asar'

with open(asar_path, 'rb') as f:
    f.read(4)
    dir_size = struct.unpack('<I', f.read(4))[0] - 8
    f.read(8)
    directory = f.read(dir_size)
    base = f.tell()

end = directory.rfind(b'}')
json_bytes = directory[:end+1]
bl = json_bytes.count(b'{')
br = json_bytes.count(b'}')
if br < bl:
    json_bytes += (bl - br) * b'}'
header = json.loads(json_bytes)
info = header['files']['out']['files']['main']['files']['main.js']
off = int(info['offset'])
sz = int(info['size'])
abs_off = base + off

with open(asar_path, 'rb') as f:
    f.seek(abs_off)
    data = f.read(sz)
s = data.decode('utf-8', 'ignore')

# 1. Multi-touch handler - get MORE context (400 chars before)
m = 'return!c.length||this._aa.sendTouch(i,c,a),!0'
idx = s.find(m)
print(f'===== MULTI-TOUCH HANDLER (marker at {idx}) =====')
if idx >= 0:
    start = max(0, idx - 500)
    end = min(len(s), idx + len(m) + 100)
    print(repr(s[start:end]))

# 2. Single-touch handler (patched) - verify it
m2 = 'console.log(s.x'
idx2 = s.find(m2)
print(f'\n===== SINGLE-TOUCH (patched, marker at {idx2}) =====')
if idx2 >= 0:
    start = max(0, idx2 - 200)
    end = min(len(s), idx2 + 200)
    print(repr(s[start:end]))

# 3. DEBUG constant
for pat in ['var DEBUG', 'const DEBUG', 'DEBUG=', 'DEBUG !', 'DEBUG=!', 'let DEBUG']:
    idx3 = s.find(pat)
    if idx3 >= 0:
        print(f'\n===== DEBUG flag (marker {pat!r} at {idx3}) =====')
        start = max(0, idx3 - 50)
        end = min(len(s), idx3 + 100)
        print(repr(s[start:end]))
        break

# 4. Look for sendMultiTouch IPC handler in main process
m4 = 'sendMultiTouch'
pos = 0
count = 0
while count < 5:
    idx4 = s.find(m4, pos)
    if idx4 < 0:
        break
    count += 1
    print(f'\n===== sendMultiTouch occurrence {count} (at {idx4}) =====')
    start = max(0, idx4 - 150)
    end = min(len(s), idx4 + 150)
    print(repr(s[start:end]))
    pos = idx4 + 1

# 5. Look for the IPC handler that receives touch from renderer
for pat in ['ipcMain', 'handle(', 'on(\"touch', 'on("touch', 'on(\'touch', 'sendTouch', 'projection:touch', 'projection-touch']:
    idx5 = s.find(pat)
    if idx5 >= 0:
        print(f'\n===== IPC pattern {pat!r} (at {idx5}) =====')
        start = max(0, idx5 - 100)
        end = min(len(s), idx5 + 200)
        print(repr(s[start:end]))
