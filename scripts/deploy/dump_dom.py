#!/usr/bin/env python3
"""Inject a DOM dump script into LIVI's renderer to see the actual DOM structure."""
import struct, json, os, sys

asar_path = '/home/raspberry/LIVI/extracted/resources/app.asar'

with open(asar_path, 'rb') as f:
    vals = struct.unpack('<IIII', f.read(16))
    json_size = vals[3]
    header_json = f.read(json_size).decode('utf-8')
    data_offset = 16 + json_size
    if data_offset % 4 != 0:
        data_offset = (data_offset + 3) & ~3

header = json.loads(header_json)

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

renderer_path = 'out/renderer/index.js'
renderer_js = None
for path, offset, size in files:
    if path == renderer_path:
        with open(asar_path, 'rb') as f:
            f.seek(data_offset + offset)
            renderer_js = f.read(size).decode('utf-8')
        break

# Find our marker and inject DOM dump right before the IIFE starts
marker = '// ===== HOME PHONE HUB v2'
idx = renderer_js.find(marker)
if idx != -1:
    # Insert a DOM dump script BEFORE our overlay
    dump_script = """
// ===== DOM DUMP (diagnostic)
(function() {
  setTimeout(function() {
    var dump = function(el, depth) {
      if (!el || depth > 5) return '';
      var s = '';
      for (var i = 0; i < el.children.length; i++) {
        var c = el.children[i];
        var id = c.id ? '#' + c.id : '';
        var cls = c.className ? '.' + String(c.className).split(' ').join('.') : '';
        var tag = c.tagName.toLowerCase();
        var style = window.getComputedStyle(c);
        var vis = style.visibility;
        var disp = style.display;
        var pos = style.position;
        var z = style.zIndex;
        s += '  '.repeat(depth) + tag + id + cls + ' [display=' + disp + ' vis=' + vis + ' pos=' + pos + ' z=' + z + ']\\n';
        s += dump(c, depth + 1);
      }
      return s;
    };
    console.log('=== DOM DUMP ===');
    console.log(dump(document.body, 0));
    console.log('=== END DOM DUMP ===');
  }, 3000);
})();
"""
    renderer_js = renderer_js[:idx] + dump_script + renderer_js[idx:]
else:
    print("ERROR: marker not found")
    sys.exit(1)

# Write back
# (We need to rebuild the asar - but for diagnostics, let's just write the JS
# and use a simpler approach: write a standalone script that LIVI's renderer
# can load)

# Actually, let's just print the first few element IDs from the compiled JS
# to understand the structure
import re
ids = re.findall(r'id=["\']([^"\']+)["\']', renderer_js[:50000])
print("IDs found in renderer JS (first 50k chars):")
for id in set(ids):
    print(f"  #{id}")

# Also search for projection-root specifically
for match in re.finditer(r'projection.root', renderer_js):
    start = max(0, match.start() - 100)
    end = min(len(renderer_js), match.end() + 100)
    print(f"\nContext around 'projection-root':")
    print(renderer_js[start:end])
    print("---")
