#!/usr/bin/env python3
"""Test night mode endpoints."""
import json, urllib.request

BASE = 'http://localhost:8123'

def get(path):
    resp = urllib.request.urlopen(BASE + path, timeout=5)
    return resp.status, json.loads(resp.read().decode())

def post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, headers={'Content-Type': 'application/json'})
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())

print('=== TEST 1: GET /api/display/nightmode ===')
code, r = get('/api/display/nightmode')
print(f'  {code}: {r}')
assert code == 200, 'FAIL'
assert 'active' in r and 'reason' in r, 'FAIL: missing active/reason'
assert 'enabled' in r and 'mode' in r, 'FAIL: missing config fields'
print('  PASS')

print('=== TEST 2: POST /api/display/nightmode (update brightness) ===')
code, r = post('/api/display/nightmode', {'brightness_pct': 50})
print(f'  {code}: {r}')
assert code == 200 and r['brightness_pct'] == 50, 'FAIL: brightness not updated'
print('  PASS')

print('=== TEST 3: POST /api/display/nightmode (update mode to on) ===')
code, r = post('/api/display/nightmode', {'mode': 'on'})
print(f'  {code}: {r}')
assert code == 200 and r['mode'] == 'on', 'FAIL: mode not updated'
assert r['active'] == True, 'FAIL: should be active when mode=on'
assert r['reason'] == 'forced-on', 'FAIL: reason should be forced-on'
print('  PASS')

print('=== TEST 4: POST /api/display/nightmode (update mode to off) ===')
code, r = post('/api/display/nightmode', {'mode': 'off'})
print(f'  {code}: {r}')
assert code == 200 and r['mode'] == 'off', 'FAIL: mode not updated'
assert r['active'] == False, 'FAIL: should be inactive when mode=off'
assert r['reason'] == 'forced-off', 'FAIL: reason should be forced-off'
print('  PASS')

print('=== TEST 5: POST /api/display/nightmode (restore to auto) ===')
code, r = post('/api/display/nightmode', {'mode': 'auto', 'brightness_pct': 35})
print(f'  {code}: {r}')
assert code == 200 and r['mode'] == 'auto', 'FAIL: mode not restored'
print('  PASS')

print('=== TEST 6: POST /api/display/nightmode (invalid mode) ===')
code, r = post('/api/display/nightmode', {'mode': 'invalid'})
print(f'  {code}: {r}')
assert code == 400, 'FAIL: invalid mode should be 400'
print('  PASS')

print('=== TEST 7: POST /api/display/nightmode (invalid brightness) ===')
code, r = post('/api/display/nightmode', {'brightness_pct': 200})
print(f'  {code}: {r}')
assert code == 400, 'FAIL: invalid brightness should be 400'
print('  PASS')

print('=== TEST 8: POST /api/display/theme (phone dark mode) ===')
code, r = post('/api/display/theme', {'dark': True})
print(f'  {code}: {r}')
assert code == 200 and r['dark'] == True, 'FAIL: theme not set'
print('  PASS')

print('=== TEST 9: POST /api/display/theme (follow-phone mode) ===')
code, r = post('/api/display/nightmode', {'mode': 'follow-phone'})
print(f'  {code}: {r}')
assert code == 200 and r['mode'] == 'follow-phone', 'FAIL: mode not set'
assert r['active'] == True, 'FAIL: should follow phone (dark=true)'
assert r['reason'] == 'follow-phone', 'FAIL: reason should be follow-phone'
print('  PASS')

print('=== TEST 10: Restore to auto ===')
code, r = post('/api/display/nightmode', {'mode': 'auto'})
print(f'  {code}: {r}')
assert code == 200, 'FAIL: restore failed'
print('  PASS')

print()
print('=' * 50)
print('ALL 10 NIGHT MODE TESTS PASSED')
print('=' * 50)
