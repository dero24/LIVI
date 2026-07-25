#!/usr/bin/env python3
"""Patch app.asar multi-touch handler to add coordinate logging (same-length).

Strategy:
  - Match the full segment including 4 trailing padding spaces from patch3.
  - Replace Math.round(r) -> r|0 and Math.round(i) -> i|0 (saves 22 chars).
  - Insert `console.log(i,c[0]);` as a separate statement before `return`.
  - i = action (DOWN=0,UP=1,MOVED=2,POINTER_DOWN=5,POINTER_UP=6)
  - c[0] = first pointer object {id,x,y} or undefined if all dropped.
"""
import json, struct, sys

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
print(f'main.js: offset={off} size={sz} abs={abs_off}')

with open(asar_path, 'rb') as f:
    f.seek(abs_off)
    data = f.read(sz)

s = data.decode('utf-8', 'ignore')
orig_len = len(s)

# --- Patch: multi-touch handler logging ---
# Current code in asar (with 4 trailing spaces from patch3):
old = (
    'c.push({id:t.id,x:Math.round(r),y:Math.round(i)})}'
    'return!c.length||this._aa.sendTouch(i,c,a),!0    '
)

# New code:
#  - Math.round(r) -> r|0, Math.round(i) -> i|0 (saves 22 chars)
#  - Insert console.log(i,c[0]); before return (costs 20 chars + 1 semicolon)
#  - Net: 22 - 21 = 1 char saved, plus 4 existing padding spaces = 3 padding spaces
new = (
    'c.push({id:t.id,x:r|0,y:i|0})}'
    'console.log(i,c[0]);'
    'return!c.length||this._aa.sendTouch(i,c,a),!0   '
)

old_len = len(old)
new_len = len(new)
print(f'\nold length: {old_len}')
print(f'new length: {new_len}')
print(f'diff: {new_len - old_len}')

if new_len != old_len:
    print(f'FATAL: length mismatch!')
    # Try to fix by adjusting padding
    if new_len < old_len:
        pad = old_len - new_len
        new = new + ' ' * pad
        new_len = len(new)
        print(f'  padded with {pad} spaces to {new_len}')
    else:
        sys.exit(1)

if new_len != old_len:
    print(f'FATAL: still mismatched {new_len} vs {old_len}')
    sys.exit(1)

idx = s.find(old)
print(f'\nold string found at index {idx}')
if idx < 0:
    print('ERROR: old string not found!')
    sys.exit(1)

print(f'  old: {old!r}')
print(f'  new: {new!r}')

# Apply
s2 = s.replace(old, new, 1)
assert len(s2) == orig_len, f'size changed: {len(s2)} vs {orig_len}'

patched = s2.encode('utf-8')
assert len(patched) == sz, f'encoded size changed: {len(patched)} vs {sz}'

with open(asar_path, 'r+b') as f:
    f.seek(abs_off)
    f.write(patched)
print(f'\nwrote {len(patched)} bytes at offset {abs_off}')
print('done — multi-touch logging patch applied')
print()
print('Log format: <action> <pointer_object_or_undefined>')
print('Actions: DOWN=0 UP=1 MOVED=2 POINTER_DOWN=5 POINTER_UP=6')
print('Example: 0 { id: 0, x: 315, y: 500 }  <- Down at (315,500)')
print('Example: 1 undefined                    <- Up but all pointers dropped')
