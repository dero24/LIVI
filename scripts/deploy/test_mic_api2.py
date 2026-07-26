#!/usr/bin/env python3
"""Test mic endpoint with error body."""
import urllib.request
import json

data = json.dumps({'source': 'bluez_input.11:11:11:00:00:00'}).encode()
req = urllib.request.Request('http://localhost:8123/api/audio/test-mic', data=data, headers={'Content-Type': 'application/json'})
try:
    resp = urllib.request.urlopen(req, timeout=15)
    print(f"Status: {resp.status}")
    print(resp.read().decode())
except urllib.error.HTTPError as e:
    print(f"HTTP Error: {e.code}")
    print(e.read().decode())
