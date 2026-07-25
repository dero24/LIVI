#!/usr/bin/env python3
import json, os, shutil, struct, sys

asar_path = '/home/raspberry/LIVI/extracted/resources/app.asar'
unpacked_dir = '/home/raspberry/LIVI/extracted/resources/app.asar.unpacked'
out_file = '/tmp/main.js.orig'

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
        children[name] = {'size': sz, 'unpacked': True}

# Read asar header
with open(asar_path, 'rb') as f:
    header1 = struct.unpack('<I', f.read(4))[0]
    size_field = struct.unpack('<I', f.read(4))[0]
    dir_size = size_field - 8
    skip8 = f.read(8)
    directory = f.read(dir_size)
    base = f.tell()

# Trim and parse JSON
end = directory.rfind(b'}')
json_bytes = directory[:end+1]
bl = json_bytes.count(b'{')
br = json_bytes.count(b'}')
if br < bl:
    json_bytes += (bl - br) * b'}'
header = json.loads(json_bytes)

# Extract main.js
info = lookup(header, ['out', 'main', 'main.js'])
if not info:
    print('main.js not found in asar')
    sys.exit(1)
off = int(info['offset'])
sz = int(info['size'])
with open(asar_path, 'rb') as f:
    f.seek(base + off)
    data = f.read(sz)
open(out_file, 'wb').write(data)
print(f'extracted {out_file} {sz} bytes')

# Copy to unpacked location
unpacked_path = os.path.join(unpacked_dir, 'out', 'main', 'main.js')
os.makedirs(os.path.dirname(unpacked_path), exist_ok=True)
shutil.copy(out_file, unpacked_path)
print(f'copied to {unpacked_path}')

# Update header
set_unpacked(header, ['out', 'main', 'main.js'])

# Build new JSON, pad to original directory length
new_json = json.dumps(header, separators=(',', ':')).encode('utf-8')
if len(new_json) > dir_size:
    print(f'new json {len(new_json)} larger than original {dir_size}; cannot keep offsets')
    sys.exit(1)
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
print('updated app.asar header')
