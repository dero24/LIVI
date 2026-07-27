#!/usr/bin/env python3
"""Check what's actually in the deployed renderer."""
import struct, json

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

for path, offset, size in files:
    if path != 'out/renderer/index.js':
        continue
    with open(asar_path, 'rb') as f:
        f.seek(data_offset + offset)
        content = f.read(size).decode('utf-8', errors='ignore')

    print(f"Renderer size: {len(content)} chars")

    # Check for all the new features
    checks = [
        ('Overlay marker', '// ===== HOME PHONE HUB'),
        ('homehubOpenNotifications', 'homehubOpenNotifications'),
        ('homehubOpenFullApps', 'homehubOpenFullApps'),
        ('startNotifsCalibration', 'startNotifsCalibration'),
        ('Calibrate Notifications button', 'Calibrate Notifications'),
        ('setupAaCallListener', 'setupAaCallListener'),
        ('aaCallerId', 'aaCallerId'),
        ('type: call event', "type:`call`"),
        ("type: 'call' event", "type:'call'"),
        ('getNotifsPos', 'getNotifsPos'),
        ('saveNotifsPos', 'saveNotifsPos'),
        ('sendTouchAt', 'sendTouchAt'),
        ('homehubOpenSettings', 'homehubOpenSettings'),
        ('Settings overlay', 'homehub-settings-overlay'),
        ('Re-calibrate Apps', 'Re-calibrate Apps'),
        ('Forget Phone', 'Forget Phone'),
        ('pollStatus', 'pollStatus'),
        ('pollTimer', 'pollTimer'),
        ('start() function', 'function start()'),
        ('HomeHub v2 started', 'HomeHub v2'),
        ('HomePhone started', 'HomePhone'),
    ]

    for label, marker in checks:
        idx = content.find(marker)
        if idx != -1:
            print(f"  [OK] {label}: at offset {idx}")
        else:
            print(f"  [MISSING] {label}: NOT FOUND")

    # Show the last 200 chars
    print(f"\n=== Last 200 chars ===")
    print(repr(content[-200:]))

    # Check if start() is called
    start_call_idx = content.rfind('start()')
    if start_call_idx != -1:
        print(f"\nLast start() call at offset {start_call_idx}")
        s = max(0, start_call_idx - 100)
        e = min(len(content), start_call_idx + 100)
        print(f"Context: {content[s:e]}")

    break
