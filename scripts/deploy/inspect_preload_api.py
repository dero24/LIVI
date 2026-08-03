#!/usr/bin/env python3
"""Inspect preload API split + our ring banner answer mechanism."""
import struct, json, re

ASAR = '/home/raspberry/LIVI/extracted/resources/app.asar'
with open(ASAR, 'rb') as f:
    vals = struct.unpack('<IIII', f.read(16))
    header = json.loads(f.read(vals[3]).decode('utf-8'))
    do = 16 + vals[3]
    if do % 4: do = (do + 3) & ~3

def collect(node, path=''):
    r = []
    if 'files' in node:
        for n, c in node['files'].items():
            f2 = path + '/' + n
            if 'files' in c: r.extend(collect(c, f2))
            else: r.append((f2, int(c.get('offset', 0)), int(c.get('size', 0))))
    return r

files = collect(header)
def read(p):
    for path, off, size in files:
        if path == p:
            with open(ASAR, 'rb') as f:
                f.seek(do + off); return f.read(size).decode('utf-8', errors='ignore')
    return None

pre = read('/out/preload/index.js')
print('=== FULL PRELOAD (the real API contract) ===')
print(pre)

renderer = read('/out/renderer/index.js')
idx = renderer.find('// ===== HOME PHONE HUB')
our = renderer[idx:]

print('\n\n=== OUR RING BANNER: how do we answer/decline? ===')
for kw in ['answerCall', 'declineCall', 'homehubAnswer', 'homehubDecline', 'acceptCall', 'rejectCall']:
    for m in re.finditer(r'function\s+' + kw + r'\s*\([^)]*\)\s*\{', our):
        s = m.start(); d = 0; i = our.index('{', s)
        for j in range(i, min(i+3000, len(our))):
            if our[j] == '{': d += 1
            elif our[j] == '}':
                d -= 1
                if d == 0:
                    print(f'\n--- {kw} ---')
                    print(our[s:j+1]); break

print('\n\n=== OUR sendCmd() — what does it wrap? ===')
m = re.search(r'function sendCmd\s*\([^)]*\)\s*\{', our)
if m:
    s = m.start(); d = 0; i = our.index('{', s)
    for j in range(i, min(i+2000, len(our))):
        if our[j] == '{': d += 1
        elif our[j] == '}':
            d -= 1
            if d == 0: print(our[s:j+1]); break

print('\n\n=== ALL sendCommand() ARGS OUR OVERLAY USES ===')
print(sorted(set(re.findall(r"sendCommand\(\s*['\"`](\w+)['\"`]", our))))
print('via sendCmd():', sorted(set(re.findall(r"sendCmd\(\s*['\"`](\w+)['\"`]", our))))

print('\n\n=== LIVI CommandMapping (valid sendCommand keys) ===')
main = read('/out/main/main.js')
# The command enum: e[e.name=N]=`name`
cmds = re.findall(r'e\[e\.(\w+)\s*=\s*(\d+)\]\s*=\s*[`\'"]\1[`\'"]', main)
for name, num in cmds:
    print(f'  {num:>4}  {name}')
