#!/usr/bin/env python3
"""Test mic endpoint."""
import urllib.request
import json

data = json.dumps({'source': 'bluez_input.11:11:11:00:00:00'}).encode()
req = urllib.request.Request('http://localhost:8123/api/audio/test-mic', data=data, headers={'Content-Type': 'application/json'})
resp = urllib.request.urlopen(req, timeout=15)
print(resp.read().decode())
