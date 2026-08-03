#!/usr/bin/env python3
"""Toggle night mode off, wait 15s, screenshot, toggle on, wait 15s, screenshot.
Then compare brightness to verify the dimming overlay is working."""
import json, urllib.request, subprocess, time, struct, zlib

BASE = 'http://localhost:8123'

def post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, headers={'Content-Type': 'application/json'})
    resp = urllib.request.urlopen(req, timeout=5)
    return json.loads(resp.read().decode())

def screenshot(name):
    subprocess.run(['python3', '/home/raspberry/take_screenshot.py'], capture_output=True, timeout=10)
    subprocess.run(['cp', '/tmp/homehub_screenshot0.png', f'/tmp/{name}.png'], timeout=5)
    print(f'  Screenshot: /tmp/{name}.png')

def avg_brightness(path):
    with open(path, 'rb') as f:
        data = f.read()
    ihdr_idx = data.find(b'IHDR')
    w = struct.unpack('>I', data[ihdr_idx+4:ihdr_idx+8])[0]
    h = struct.unpack('>I', data[ihdr_idx+8:ihdr_idx+12])[0]
    idat = b''
    idx = 0
    while True:
        idat_idx = data.find(b'IDAT', idx)
        if idat_idx == -1: break
        chunk_len = struct.unpack('>I', data[idat_idx-4:idat_idx])[0]
        idat += data[idat_idx+4:idat_idx+4+chunk_len]
        idx = idat_idx + 4 + chunk_len
    raw = zlib.decompress(idat)
    stride = w * 3 + 1
    total = 0
    count = 0
    for y in range(h):
        row_start = y * stride
        for x in range(w):
            i = row_start + 1 + x * 3
            total += (raw[i] + raw[i+1] + raw[i+2]) / 3
            count += 1
    return total / count if count > 0 else 0

# Force night mode OFF, wait for overlay to pick up (polls every 10s)
print('Forcing night mode OFF...')
r = post('/api/display/nightmode', {'mode': 'off'})
print(f'  active={r["active"]}, reason={r["reason"]}')
print('  Waiting 15s for overlay to poll...')
time.sleep(15)
screenshot('nightmode_off')

# Force night mode ON, wait for overlay
print('Forcing night mode ON...')
r = post('/api/display/nightmode', {'mode': 'on'})
print(f'  active={r["active"]}, reason={r["reason"]}')
print('  Waiting 15s for overlay to poll...')
time.sleep(15)
screenshot('nightmode_on')

# Restore to auto
print('Restoring to auto...')
r = post('/api/display/nightmode', {'mode': 'auto'})
print(f'  active={r["active"]}, reason={r["reason"]}')

# Compare brightness
off_b = avg_brightness('/tmp/nightmode_off.png')
on_b = avg_brightness('/tmp/nightmode_on.png')
print()
print(f'nightmode_off avg brightness: {off_b:.1f}/255')
print(f'nightmode_on  avg brightness: {on_b:.1f}/255')
diff = off_b - on_b
pct = (diff / off_b * 100) if off_b > 0 else 0
print(f'Difference: {diff:.1f} ({pct:.1f}% dimmer)')
if on_b < off_b - 1:
    print('PASS: night mode ON is dimmer than OFF')
else:
    print('FAIL: no visible dimming difference')
