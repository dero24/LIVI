#!/usr/bin/env python3
"""Test script for v0.4 sidecar endpoints. Run ON the Pi."""
import json
import urllib.request

BASE = 'http://localhost:8123'

def post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, headers={'Content-Type': 'application/json'})
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())
    except Exception as e:
        return None, str(e)

def get(path):
    try:
        resp = urllib.request.urlopen(BASE + path, timeout=5)
        return resp.status, json.loads(resp.read().decode())
    except Exception as e:
        return None, str(e)

print('=== TEST 1: POST /media (add) ===')
code, r = post('/media', {'title': 'Bohemian Rhapsody', 'artist': 'Queen', 'app': 'Spotify', 'playing': True})
print(f'  {code}: {r}')
assert code == 200 and r.get('status') == 'ok', 'FAIL: media add'
assert r.get('media', {}).get('title') == 'Bohemian Rhapsody', 'FAIL: media title missing'
print('  PASS')

print('=== TEST 2: GET /status (media should be present) ===')
code, r = get('/status')
print(f'  {code}: media={r.get("media")}')
assert code == 200, 'FAIL: status'
assert r.get('media') is not None, 'FAIL: media should be in status'
assert r['media']['title'] == 'Bohemian Rhapsody', 'FAIL: media title in status'
assert r['media']['source'] == 'companion', 'FAIL: media source'
print('  PASS')

print('=== TEST 3: POST /notifs (add) ===')
code, r = post('/notifs', {'action': 'add', 'id': 'test1', 'title': 'Mom', 'text': 'Call me when you can', 'app': 'WhatsApp', 'platform': 'android'})
print(f'  {code}: {r}')
assert code == 200 and r.get('status') == 'ok', 'FAIL: notif add'
assert r.get('notification', {}).get('title') == 'Mom', 'FAIL: notif title'
print('  PASS')

print('=== TEST 4: POST /notifs (add second, iPhone/ANCS) ===')
code, r = post('/notifs', {'action': 'add', 'id': 'test2', 'title': 'Slack', 'text': 'New message in #general', 'app': 'Slack', 'platform': 'iphone'})
print(f'  {code}: {r}')
assert code == 200, 'FAIL: notif add 2'
print('  PASS')

print('=== TEST 5: GET /status (notifications should have 2, newest first) ===')
code, r = get('/status')
notifs = r.get('notifications', [])
print(f'  {code}: {len(notifs)} notifs: {[n["title"] for n in notifs]}')
assert len(notifs) == 2, 'FAIL: should have 2 notifs'
print('  PASS')

print('=== TEST 6: POST /notifs (update existing id) ===')
code, r = post('/notifs', {'action': 'add', 'id': 'test1', 'title': 'Mom (updated)', 'text': 'Actually never mind', 'app': 'WhatsApp', 'platform': 'android'})
print(f'  {code}: {r}')
code, r = get('/status')
notifs = r.get('notifications', [])
titles = [n['title'] for n in notifs]
print(f'  notifs after update: {titles}')
assert len(notifs) == 2, 'FAIL: update should not add new entry'
assert 'Mom (updated)' in titles, 'FAIL: title should be updated'
print('  PASS')

print('=== TEST 7: POST /notifs (remove) ===')
code, r = post('/notifs', {'action': 'remove', 'id': 'test1'})
print(f'  {code}: {r}')
assert code == 200 and r.get('removed') == 1, 'FAIL: notif remove'
code, r = get('/status')
notifs = r.get('notifications', [])
assert len(notifs) == 1, 'FAIL: should have 1 notif after remove'
print('  PASS')

print('=== TEST 8: POST /notifs (clear all) ===')
code, r = post('/notifs', {'action': 'clear'})
print(f'  {code}: {r}')
assert code == 200, 'FAIL: notif clear'
code, r = get('/status')
notifs = r.get('notifications', [])
assert len(notifs) == 0, 'FAIL: should have 0 notifs after clear'
print('  PASS')

print('=== TEST 9: POST /media (clear) ===')
code, r = post('/media', {'clear': True})
print(f'  {code}: {r}')
assert code == 200 and r.get('media') is None, 'FAIL: media clear'
code, r = get('/status')
assert r.get('media') is None, 'FAIL: media should be null after clear'
print('  PASS')

print('=== TEST 10: POST /notifs (empty body → 400) ===')
code, r = post('/notifs', {})
print(f'  {code}: {r}')
assert code == 400, 'FAIL: empty body should be 400'
print('  PASS')

print('=== TEST 11: POST /dock (missing mac → 400) ===')
code, r = post('/dock', {'name': 'Test Phone'})
print(f'  {code}: {r}')
assert code == 400, 'FAIL: dock without mac should be 400'
print('  PASS')

print('=== TEST 12: GET /status (final clean state) ===')
code, r = get('/status')
print(f'  {code}: {json.dumps(r, indent=2)}')
assert r.get('media') is None, 'FAIL: media should be null'
assert r.get('notifications') == [], 'FAIL: notifs should be empty'
assert r.get('dock') == {}, 'FAIL: dock should be empty'
print('  PASS')

print()
print('=' * 50)
print('ALL 12 TESTS PASSED')
print('=' * 50)
