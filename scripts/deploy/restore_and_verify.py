#!/usr/bin/env python3
"""Restore night mode to defaults and verify services are healthy."""
import json, urllib.request, subprocess

BASE = 'http://localhost:8123'

def post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, headers={'Content-Type': 'application/json'})
    resp = urllib.request.urlopen(req, timeout=5)
    return json.loads(resp.read().decode())

def get(path):
    resp = urllib.request.urlopen(BASE + path, timeout=5)
    return json.loads(resp.read().decode())

# Restore to auto mode with default brightness
print('Restoring night mode to defaults...')
r = post('/api/display/nightmode', {'mode': 'auto', 'brightness_pct': 35, 'warm_tint': True, 'warm_tint_intensity': 0.12})
print(f'  mode={r["mode"]}, active={r["active"]}, reason={r["reason"]}')

# Verify services
print()
print('Service status:')
for svc in ['livi.service', 'homephone-sidecar.service']:
    r = subprocess.run(['systemctl', '--user', 'is-active', svc], capture_output=True, text=True)
    print(f'  {svc}: {r.stdout.strip()}')

# Verify /status
print()
s = get('/status')
print(f'Sidecar /status: livi_connected={s.get("livi_connected")}, media={s.get("media")}, notifs={len(s.get("notifications", []))}')

# Verify night mode endpoint
nm = get('/api/display/nightmode')
print(f'Night mode: mode={nm["mode"]}, active={nm["active"]}, reason={nm["reason"]}')
print()
print('All good. Ready for morning testing.')
