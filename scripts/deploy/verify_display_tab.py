#!/usr/bin/env python3
"""Verify night mode endpoint + settings page Display tab."""
import json, urllib.request

BASE = 'http://localhost:8123'

def get(path):
    return json.loads(urllib.request.urlopen(BASE + path, timeout=5).read().decode())

def post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, headers={'Content-Type': 'application/json'})
    try:
        return urllib.request.urlopen(req, timeout=5).read().decode()
    except urllib.error.HTTPError as e:
        return f'HTTP {e.code}: {e.read().decode()}'

# 1. Night mode GET
print('=== Night mode config ===')
nm = get('/api/display/nightmode')
print(f'  mode={nm["mode"]}, active={nm["active"]}, reason={nm["reason"]}')
print(f'  enabled={nm["enabled"]}, brightness={nm["brightness_pct"]}%, warm_tint={nm["warm_tint"]}')
assert 'follow-phone' not in nm.get('reason', ''), 'FAIL: follow-phone should not appear'
print('  PASS: no follow-phone in response')

# 2. Follow-phone should be rejected
print()
print('=== Follow-phone rejection ===')
r = post('/api/display/nightmode', {'mode': 'follow-phone'})
if '400' in r:
    print(f'  PASS: rejected — {r}')
else:
    print(f'  FAIL: accepted — {r}')

# 3. Settings page has Display tab
print()
print('=== Settings page Display tab ===')
html = urllib.request.urlopen(BASE + '/settings', timeout=5).read().decode()
checks = [
    ('data-tab="display"', 'Display tab button'),
    ('loadDisplay', 'loadDisplay function'),
    ('nm-enabled', 'Night mode enable checkbox'),
    ('nm-brightness', 'Brightness slider'),
    ('nm-warm-tint', 'Warm tint toggle'),
    ('nm-start', 'Start time input'),
    ('nm-end', 'End time input'),
    ('previewNightMode', 'Preview buttons'),
    ('slider-toggle', 'Toggle switch CSS'),
    ('btn-toggle', 'Toggle button CSS'),
]
all_pass = True
for marker, desc in checks:
    found = marker in html
    status = 'PASS' if found else 'FAIL'
    if not found: all_pass = False
    print(f'  {status}: {desc}')
    if not found:
        # Show context around where it should be
        print(f'    (searching for: {marker})')

print()
if all_pass:
    print('ALL CHECKS PASSED — settings page Display tab is ready')
else:
    print('SOME CHECKS FAILED — see above')
