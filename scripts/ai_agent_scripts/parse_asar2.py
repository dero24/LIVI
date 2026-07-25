#!/usr/bin/env python3
import json, struct
p = '/home/raspberry/LIVI/extracted/resources/app.asar'
with open(p, 'rb') as f:
    v1 = struct.unpack('<I', f.read(4))[0]
    size = struct.unpack('<I', f.read(4))[0] - 8
    f.read(8)
    directory = f.read(size)
    base = f.tell()
print('v1', v1, 'dir size', size, 'base', base)
end = directory.rfind(b'}')
directory = directory[:end+1]
# balance braces if needed
bl = directory.count(b'{')
br = directory.count(b'}')
if br < bl:
    directory += (bl - br) * b'}'
header = json.loads(directory)
print('integrity present:', 'integrity' in json.dumps(header)[:5000])
# walk and find file containing 'AOAP re-enumerate timeout'
def walk(d, path=''):
    for name, info in d.get('files', {}).items():
        p2 = path + '/' + name if path else name
        if 'files' in info:
            walk(info, p2)
        else:
            if 'size' in info:
                print(p2, 'offset', info.get('offset'), 'size', info.get('size'))
walk(header)
