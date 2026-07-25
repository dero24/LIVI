#!/usr/bin/env python3
import json, struct, sys
p = '/home/raspberry/LIVI/extracted/resources/app.asar'
subpath = sys.argv[1]
out = sys.argv[2]
with open(p, 'rb') as f:
    v1 = struct.unpack('<I', f.read(4))[0]
    size = struct.unpack('<I', f.read(4))[0] - 8
    f.read(8)
    directory = f.read(size)
    base = f.tell()
end = directory.rfind(b'}')
directory = directory[:end+1]
bl = directory.count(b'{')
br = directory.count(b'}')
if br < bl:
    directory += (bl - br) * b'}'
header = json.loads(directory)

def lookup(d, parts):
    if not parts:
        return d
    name = parts[0]
    rest = parts[1:]
    children = d.get('files', {})
    if name not in children:
        return None
    info = children[name]
    if 'files' in info:
        return lookup(info, rest)
    return info

info = lookup(header, subpath.split('/'))
print('info:', json.dumps(info)[:500])
if not info or 'size' not in info:
    print('not found')
    sys.exit(1)
off = int(info['offset'])
sz = int(info['size'])
f.seek(base + off)
data = f.read(sz)
open(out, 'wb').write(data)
print(f'wrote {out} {sz} bytes')
