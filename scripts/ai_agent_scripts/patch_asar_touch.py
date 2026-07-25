#!/usr/bin/env python3
"""In-place binary patch of app.asar — exact same-length replacements."""
import json, struct

asar_path = '/home/raspberry/LIVI/extracted/resources/app.asar'

# Read asar header to find main.js offset
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

# --- Patch 1: single-touch sendTouch + log ---
# Replace Math.round(x) with x|0 to save chars, use saved space for console.log
old1 = 'let s={id:0,x:Math.round(a),y:Math.round(o)};return this._aa.sendTouch(Pl(e.action),[s]),!0'
# Build replacement: same length, with a short log
# Strategy: x:a|0 saves 10, y:o|0 saves 10 = 20 chars saved
# Use those 20 chars for: console.log(s.x,s.y);  = 22 chars... need 2 more
# Also shorten return to ret? No. Use console.warn instead? Same length.
# Try: console.log(s.x,s.y) without semicolon = 21, need 20. Pad log arg.
# Actually: let's count precisely
candidate1 = 'let s={id:0,x:a|0,y:o|0};console.log(s.x,s.y);return this._aa.sendTouch(Pl(e.action),[s]),!0'
print(f'patch1: old={len(old1)} candidate={len(candidate1)} diff={len(candidate1)-len(old1)}')

if len(candidate1) > len(old1):
    diff = len(candidate1) - len(old1)
    # Need to shorten by diff chars. Remove s.y from log:
    candidate1 = 'let s={id:0,x:a|0,y:o|0};console.log(s.x,s.y);return this._aa.sendTouch(Pl(e.action),[s]),!0'
    # Try removing e.action context — already not included
    # Try shorter: just log s.x
    candidate1b = 'let s={id:0,x:a|0,y:o|0};console.log(s.x);return this._aa.sendTouch(Pl(e.action),[s]),!0'
    print(f'  candidate1b={len(candidate1b)} diff={len(candidate1b)-len(old1)}')
    if len(candidate1b) == len(old1):
        candidate1 = candidate1b
    elif len(candidate1b) < len(old1):
        # pad with spaces in the log string
        pad = len(old1) - len(candidate1b)
        candidate1 = candidate1b.replace('console.log(s.x)', f'console.log(s.x{" " * pad})')
        print(f'  padded to {len(candidate1)}')

if len(candidate1) == len(old1):
    print(f'  OK: patch1 exact match ({len(old1)} chars)')
    if old1 in s:
        s = s.replace(old1, candidate1, 1)
        print('  applied')
    else:
        print('  NOT FOUND in data')
else:
    print(f'  FAIL: cannot match length {len(old1)}')
    # Last resort: just replace Math.round with |0 without logging
    nolog1 = 'let s={id:0,x:a|0,y:o|0};return this._aa.sendTouch(Pl(e.action),[s]),!0' + ' ' * (len(old1) - len('let s={id:0,x:a|0,y:o|0};return this._aa.sendTouch(Pl(e.action),[s]),!0'))
    print(f'  nolog fallback: {len(nolog1)} (no logging, just shorter round)')

# --- Patch 2: single-touch drop + log ---
old2 = 'if(a<0||o<0||a>=t||o>=n)return!0;let s={id:0,x:Math.round(a),y:Math.round(o)}'
cand2 = "if(a<0||o<0||a>=t||o>=n){console.log('D');return!0}let s={id:0,x:a|0,y:o|0}"
print(f'patch2: old={len(old2)} cand={len(cand2)} diff={len(cand2)-len(old2)}')
if len(cand2) > len(old2):
    diff = len(cand2) - len(old2)
    # Shorten: remove 'D' -> just log empty
    cand2 = f"if(a<0||o<0||a>=t||o>=n){{console.log();return!0}}let s={{id:0,x:a|0,y:o|0}}"
    print(f'  shortened: {len(cand2)} diff={len(cand2)-len(old2)}')
if len(cand2) < len(old2):
    pad = len(old2) - len(cand2)
    cand2 = cand2.replace("console.log()", f"console.log({' ' * (pad - 2)})")
    print(f'  padded: {len(cand2)}')
if len(cand2) == len(old2):
    print(f'  OK: patch2 exact match')
    if old2 in s:
        s = s.replace(old2, cand2, 1)
        print('  applied')
    else:
        print('  NOT FOUND')

# --- Patch 3: multi-touch — skip if too complex ---
old3 = 'return c.length===0||this._aa.sendTouch(i,c,a),!0'
# Just shorten c.length===0 to !c.length (saves 4) — no logging
cand3 = 'return!c.length||this._aa.sendTouch(i,c,a),!0' + ' ' * (len(old3) - len('return!c.length||this._aa.sendTouch(i,c,a),!0'))
print(f'patch3: old={len(old3)} cand={len(cand3)} (no log, just shorter)')
if len(cand3) == len(old3) and old3 in s:
    s = s.replace(old3, cand3, 1)
    print('  applied (no log)')

# Verify total length unchanged
assert len(s) == orig_len, f'size changed: {len(s)} vs {orig_len}'
patched = s.encode('utf-8')
assert len(patched) == sz, f'encoded size changed: {len(patched)} vs {sz}'

# Write back
with open(asar_path, 'r+b') as f:
    f.seek(abs_off)
    f.write(patched)
print(f'wrote {len(patched)} bytes at offset {abs_off}')
print('done')
