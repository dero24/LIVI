#!/usr/bin/env python3
"""Restart sidecar and verify night mode + settings page."""
import subprocess, time, json, urllib.request

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)

def get(path):
    return json.loads(urllib.request.urlopen('http://localhost:8123' + path, timeout=5).read().decode())

def post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request('http://localhost:8123' + path, data=data, headers={'Content-Type': 'application/json'})
    return json.loads(urllib.request.urlopen(req, timeout=5).read().decode())

# Restart sidecar
print('Restarting sidecar...')
run('systemctl --user stop homephone-sidecar.service')
time.sleep(2)
run('fuser -k 8123/tcp 2>/dev/null')
time.sleep(1)
run('systemctl --user reset-failed homephone-sidecar.service 2>/dev/null')
run('systemctl --user start homephone-sidecar.service')
time.sleep(2)
status = run('systemctl --user is-active homephone-sidecar.service').stdout.strip()
print(f'  Sidecar: {status}')

# Test night mode endpoint
print()
nm = get('/api/display/nightmode')
print(f'Night mode: mode={nm["mode"]}, active={nm["active"]}, reason={nm["reason"]}')
print(f'  enabled={nm["enabled"]}, brightness={nm["brightness_pct"]}%, warm_tint={nm["warm_tint"]}')

# Test that follow-phone is rejected
print()
print('Testing follow-phone rejection...')
try:
    r = post('/api/display/nightmode', {'mode': 'follow-phone'})
    print(f'  ERROR: follow-phone was accepted: {r}')
except urllib.error.HTTPError as e:
    print(f'  PASS: follow-phone rejected with {e.code}')

# Test settings page loads
print()
print('Testing settings page...')
resp = urllib.request.urlopen('http://localhost:8123/settings', timeout=5)
html = resp.read().decode()
has_display_tab = 'data-tab="display"' in html
has_load_display = 'loadDisplay' in html
has_nm_enabled = 'nm-enabled' in html
print(f'  Display tab button: {"YES" if has_display_tab else "NO"}')
print(f'  loadDisplay function: {"YES" if has_load_display else "NO"}')
print(f'  nm-enabled checkbox: {"YES" if has_nm_enabled else "NO"}')

# Verify LIVI is still active
print()
livi = run('systemctl --user is-active livi.service').stdout.strip()
print(f'LIVI: {livi}')

print()
if status == 'active' and livi == 'active' and has_display_tab:
    print('ALL GOOD — ready for morning testing')
else:
    print('ISSUES DETECTED — check above')
