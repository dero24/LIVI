#!/usr/bin/env python3
import json, shutil, struct

asar_path = '/home/raspberry/LIVI/extracted/resources/app.asar'

def set_unpacked(d, parts):
    if not parts:
        return
    name = parts[0]
    rest = parts[1:]
    children = d.setdefault('files', {})
    if name not in children:
        return
    info = children[name]
    if 'files' in info:
        set_unpacked(info, rest)
    else:
        sz = info.get('size', 0)
        children[name] = {'size': sz, 'unpacked': True, 'offset': '0'}

with open(asar_path, 'rb') as f:
    header1 = struct.unpack('<I', f.read(4))[0]
    size_field = struct.unpack('<I', f.read(4))[0]
    dir_size = size_field - 8
    skip8 = f.read(8)
    directory = f.read(dir_size)
    base = f.tell()

end = directory.rfind(b'}')
json_bytes = directory[:end+1]
bl = json_bytes.count(b'{')
br = json_bytes.count(b'}')
if br < bl:
    json_bytes += (bl - br) * b'}'
header = json.loads(json_bytes)

set_unpacked(header, ['out', 'main', 'main.js'])

new_json = json.dumps(header, separators=(',', ':')).encode('utf-8')
if len(new_json) > dir_size:
    print('new json too long')
    raise SystemExit(1)
if len(new_json) < dir_size:
    new_json += b' ' * (dir_size - len(new_json))

new_asar = asar_path + '.new'
with open(asar_path, 'rb') as f_in, open(new_asar, 'wb') as f_out:
    f_out.write(struct.pack('<I', header1))
    f_out.write(struct.pack('<I', dir_size + 8))
    f_out.write(skip8)
    f_out.write(new_json)
    f_out.write(f_in.read())

shutil.move(new_asar, asar_path)
print('updated asar with offset 0 for main.js')
