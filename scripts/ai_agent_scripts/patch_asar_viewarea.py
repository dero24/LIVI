#!/usr/bin/env python3
"""
Patch the app.asar to fold projectionViewArea insets into:
1. ProjectionService video crop (main process)
2. Projection.tsx touch transform (renderer)

This enables cropping the center strip from a square AA render to fill a portrait screen.
"""
import struct, json, os, sys, shutil, time

asar_path = '/home/raspberry/LIVI/extracted/resources/app.asar'
backup_path = '/home/raspberry/LIVI/extracted/resources/app.asar.bak.viewarea'

# --- Parse the asar ---
with open(asar_path, 'rb') as f:
    vals = struct.unpack('<IIII', f.read(16))
    json_size = vals[3]
    header_json = f.read(json_size).decode('utf-8')
    data_offset = 16 + json_size
    if data_offset % 4 != 0:
        data_offset = (data_offset + 3) & ~3

header = json.loads(header_json)

# Recursively collect all files with their offsets
def collect_files(node, prefix=''):
    results = []
    if 'files' in node:
        for name, child in node['files'].items():
            path = f"{prefix}/{name}" if prefix else name
            if 'files' in child:
                results.extend(collect_files(child, path))
            elif 'offset' in child:
                results.append((path, int(child['offset']), child.get('size', 0)))
    return results

files = collect_files(header)
print(f"Total files in asar: {len(files)}")

# --- Read the two files we need to patch ---
main_js_path = 'out/main/main.js'
renderer_js_path = 'out/renderer/index.js'

main_js = None
renderer_js = None

for path, offset, size in files:
    if path == main_js_path:
        with open(asar_path, 'rb') as f:
            f.seek(data_offset + offset)
            main_js = f.read(size).decode('utf-8')
        print(f"Read {main_js_path}: {len(main_js)} chars")
    elif path == renderer_js_path:
        with open(asar_path, 'rb') as f:
            f.seek(data_offset + offset)
            renderer_js = f.read(size).decode('utf-8')
        print(f"Read {renderer_js_path}: {len(renderer_js)} chars")

if not main_js or not renderer_js:
    print("ERROR: Could not find target files!")
    sys.exit(1)

# --- Patch 1: Main process - video crop ---
# Original: this.videoCrop={cropL:Math.max(0,(e-i)/2),cropT:Math.max(0,(t-a)/2),visW:i,visH:a,tierW:e,tierH:t}
# New: fold projectionViewArea insets into the crop
old_main = 'this.videoCrop={cropL:Math.max(0,(e-i)/2),cropT:Math.max(0,(t-a)/2),visW:i,visH:a,tierW:e,tierH:t}'

# n=projectionWidth, r=projectionHeight, i=contentWidth, a=contentHeight
# inset in content space = display_inset * (contentSize / displaySize)
new_main = ('this.videoCrop={cropL:Math.max(0,(e-i)/2)+(this.config.projectionViewAreaLeft??0)*(i/n),'
            'cropT:Math.max(0,(t-a)/2)+(this.config.projectionViewAreaTop??0)*(a/r),'
            'visW:i-(this.config.projectionViewAreaLeft??0)*(i/n)-(this.config.projectionViewAreaRight??0)*(i/n),'
            'visH:a-(this.config.projectionViewAreaTop??0)*(a/r)-(this.config.projectionViewAreaBottom??0)*(a/r),'
            'tierW:e,tierH:t}')

if old_main in main_js:
    main_js = main_js.replace(old_main, new_main, 1)
    print(f"Patched main.js: video crop with view area insets")
else:
    print("ERROR: Could not find video crop pattern in main.js!")
    sys.exit(1)

# --- Patch 2: Renderer - touch transform ---
# Original: cropLeft:Math.max(0,(H-ie)/2),cropTop:Math.max(0,(ne-ae)/2),visibleWidth:ie,visibleHeight:ae
old_renderer = 'cropLeft:Math.max(0,(H-ie)/2),cropTop:Math.max(0,(ne-ae)/2),visibleWidth:ie,visibleHeight:ae'

# n=settings (has projectionWidth, projectionHeight, projectionViewArea*)
# H=negotiatedWidth, ne=negotiatedHeight, ie=contentWidth, ae=contentHeight
new_renderer = ('cropLeft:Math.max(0,(H-ie)/2)+(n.projectionViewAreaLeft??0)*(ie/n.projectionWidth),'
                'cropTop:Math.max(0,(ne-ae)/2)+(n.projectionViewAreaTop??0)*(ae/n.projectionHeight),'
                'visibleWidth:ie-(n.projectionViewAreaLeft??0)*(ie/n.projectionWidth)-(n.projectionViewAreaRight??0)*(ie/n.projectionWidth),'
                'visibleHeight:ae-(n.projectionViewAreaTop??0)*(ae/n.projectionHeight)-(n.projectionViewAreaBottom??0)*(ae/n.projectionHeight)')

if old_renderer in renderer_js:
    renderer_js = renderer_js.replace(old_renderer, new_renderer, 1)
    print(f"Patched renderer.js: touch transform with view area insets")
else:
    print("ERROR: Could not find touch transform pattern in renderer.js!")
    sys.exit(1)

# --- Rebuild the asar ---
print("\nRebuilding asar...")

# Back up original
if not os.path.exists(backup_path):
    shutil.copy2(asar_path, backup_path)
    print(f"Backed up to {backup_path}")

# Build new asar: header JSON + file data
# First, collect all file data in order
file_data_list = []
new_header = json.loads(header_json)  # Deep copy

def rebuild_node(node, files_map):
    """Update offsets and sizes in the header."""
    if 'files' not in node:
        return
    current_offset = 0
    for name, child in node['files'].items():
        if 'files' in child:
            rebuild_node(child, files_map)
        elif 'offset' in child:
            path_data = files_map.get((name, child.get('offset')))
            # We'll update offsets in a second pass

# Simpler approach: rebuild the entire file data section
# Collect all files in order, update their offsets
all_files_sorted = sorted(files, key=lambda x: x[1])  # Sort by original offset

new_data = bytearray()
offset_map = {}  # old (path) -> new offset

for path, old_offset, old_size in all_files_sorted:
    if path == main_js_path:
        content = main_js.encode('utf-8')
    elif path == renderer_js_path:
        content = renderer_js.encode('utf-8')
    else:
        with open(asar_path, 'rb') as f:
            f.seek(data_offset + old_offset)
            content = f.read(old_size)
    
    new_offset = len(new_data)
    offset_map[path] = (new_offset, len(content))
    new_data.extend(content)
    # Pad to 4-byte alignment
    while len(new_data) % 4 != 0:
        new_data.append(0)

# Update header with new offsets and sizes
def update_header(node, prefix=''):
    if 'files' not in node:
        return
    for name, child in node['files'].items():
        path = f"{prefix}/{name}" if prefix else name
        if 'files' in child:
            update_header(child, path)
        elif 'offset' in child:
            if path in offset_map:
                new_off, new_size = offset_map[path]
                child['offset'] = str(new_off)
                child['size'] = new_size

update_header(header)

# Build new asar file
header_json_new = json.dumps(header, separators=(',', ':')).encode('utf-8')
json_size = len(header_json_new)
# Pad JSON to 4-byte alignment
padding = (4 - (json_size % 4)) % 4
header_padded = header_json_new + b'\x00' * padding
padded_size = json_size + padding

# ASAR header format (Chromium Pickle):
# uint32_t: 4 (size of the payload_size field that follows)
# uint32_t: payload_size = 8 + padded_size (everything after this field)
# uint32_t: header_string_size = 4 + padded_size (json_size field + padded JSON)
# uint32_t: json_size (actual JSON size without padding)
# then padded JSON
payload_size = 8 + padded_size
header_string_size = 4 + padded_size

asar_header = struct.pack('<IIII', 4, payload_size, header_string_size, json_size)
asar_header += header_padded

# Write the new asar
tmp_path = asar_path + '.tmp'
with open(tmp_path, 'wb') as f:
    f.write(asar_header)
    f.write(new_data)

# Verify
with open(tmp_path, 'rb') as f:
    verify_vals = struct.unpack('<IIII', f.read(16))
    verify_json_size = verify_vals[3]
    verify_json = f.read(verify_json_size).decode('utf-8')
    verify_header = json.loads(verify_json)
    print(f"Verification: header parsed OK, {len(verify_json)} bytes JSON")

# Replace original
os.replace(tmp_path, asar_path)
print(f"\nDone! New asar written to {asar_path}")
print(f"Original backed up to {backup_path}")
print(f"\nNow set projectionViewAreaLeft=212, projectionViewAreaRight=212 in config.json")
print("and restart LIVI to test the cropped center strip.")
