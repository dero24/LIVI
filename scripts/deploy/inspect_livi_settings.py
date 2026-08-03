#!/usr/bin/env python3
"""Deep inspect LIVI's native renderer settings UI."""
import struct, json, re

ASAR = '/home/raspberry/LIVI/extracted/resources/app.asar'

with open(ASAR, 'rb') as f:
    vals = struct.unpack('<IIII', f.read(16))
    header = json.loads(f.read(vals[3]).decode('utf-8'))
    data_offset = 16 + vals[3]
    if data_offset % 4 != 0:
        data_offset = (data_offset + 3) & ~3

def collect(node, path=''):
    result = []
    if 'files' in node:
        for name, child in node['files'].items():
            full = path + '/' + name
            if 'files' in child:
                result.extend(collect(child, full))
            else:
                result.append((full, int(child.get('offset', 0)), int(child.get('size', 0))))
    return result

files = collect(header)

# Read renderer index.js
for path, offset, size in files:
    if path == '/out/renderer/index.js':
        with open(ASAR, 'rb') as f:
            f.seek(data_offset + offset)
            js = f.read(size).decode('utf-8', errors='ignore')
        break

print(f'Renderer: {len(js)} chars')

# Search for settings page labels/sections
# LIVI uses React with MUI, so look for label strings
labels_to_find = [
    'WiFi Channel', 'WiFi Password', 'WiFi Band', 'wifiInterface',
    'Wireless Android Auto', 'Wireless CarPlay', 'wirelessAaEnabled',
    'wirelessCpEnabled', 'Auto Connect', 'autoConn', 'Car Name', 'carName',
    'Bluetooth', 'Paired', 'pair', 'Settings', 'settings',
    'WiFi Interface', 'wifiType', '5ghz', '2.4ghz',
    'Dedicated Interface', 'hostapd', 'access point', 'Access Point',
    'BT Adapter', 'btAdapter', 'Discoverable', 'discoverable',
    'Phone', 'phone', 'Session', 'session', 'Device', 'device',
    'battery', 'Battery', 'signal', 'Signal',
    'Audio', 'audio', 'Display', 'display', 'Night Mode',
    'System', 'system', 'About', 'about',
    'WiFi', 'wifi', 'Connect', 'connect',
]

print('\n=== Settings UI labels found in renderer ===')
for label in labels_to_find:
    matches = list(re.finditer(re.escape(label), js, re.IGNORECASE))
    if matches:
        # Show unique contexts
        seen = set()
        for m in matches[:3]:
            start = max(0, m.start() - 60)
            end = min(len(js), m.end() + 80)
            ctx = js[start:end].replace('\n', ' ').strip()
            if ctx not in seen:
                seen.add(ctx)
                print(f'  [{label}]: ...{ctx}...')

# Search for settings page sections/routes
print('\n=== Settings routes/sections ===')
for pattern in [r'path:["\']([^"\']*setting[^"\']*)["\']',
                r'route["\']?[:=]["\']([^"\']*)["\']',
                r'tab[s]?:\s*\[',
                r'section[s]?:\s*\[',
                r'label:["\']([^"\']{3,30})["\']',
                r'title:["\']([^"\']{3,30})["\']',
                r'["\']([A-Z][a-z]+ [A-Z][a-z]+)["\']',  # "Word Word" labels
                ]:
    matches = list(re.finditer(pattern, js))
    if matches:
        seen = set()
        for m in matches[:15]:
            val = m.group(0)[:100]
            if val not in seen:
                seen.add(val)
                print(f'  {val}')

# Look for settings tab/panel names
print('\n=== Tab/Panel labels ===')
for m in re.finditer(r'(?:label|title|name):\s*["`]([^"`]{2,40})["`]', js):
    val = m.group(1)
    if any(c.isupper() for c in val) and not val.startswith('_') and not val.startswith('use'):
        print(f'  {val}')

# Search for the settings save function
print('\n=== Settings save/config functions ===')
for kw in ['settings.save', 'saveConfig', 'updateConfig', 'setConfig', 'config.save',
           'writeConfig', 'persistConfig', 'saveSettings']:
    if kw in js:
        idx = js.find(kw)
        ctx = js[max(0,idx-80):idx+120].replace('\n',' ')
        print(f'  [{kw}]: ...{ctx}...')
