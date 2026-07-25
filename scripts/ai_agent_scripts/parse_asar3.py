#!/usr/bin/env python3
import json, struct
p = '/home/raspberry/LIVI/extracted/resources/app.asar'
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
# find main.js
def find(d, path=''):
    for name, info in d.get('files', {}).items():
        p2 = path + '/' + name if path else name
        if 'files' in info:
            r = find(info, p2)
            if r: return r
        else:
            if p2.endswith('out/main/main.js'):
                return info
    return None
info = find(header)
print('main.js info:', json.dumps(info, indent=2)[:2000])
print('base offset', base)
