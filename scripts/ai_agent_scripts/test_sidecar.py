#!/usr/bin/env python3
"""Test the sidecar by sending a ring request."""
import urllib.request
import urllib.parse
import json
import time

# Wait for sidecar to be up
time.sleep(1)

# Send a ring
url = 'http://localhost:8123/ring?slot=1&caller=TestCaller&phone=TestPhone'
req = urllib.request.Request(url, method='POST', data=b'')
try:
    resp = urllib.request.urlopen(req, timeout=5)
    print(f'Ring response: {resp.status} {resp.read().decode()}')
except Exception as e:
    print(f'Ring failed: {e}')

time.sleep(1)

# Check status
try:
    resp = urllib.request.urlopen('http://localhost:8123/status', timeout=5)
    data = json.loads(resp.read().decode())
    print(f'Status: {json.dumps(data, indent=2)}')
except Exception as e:
    print(f'Status failed: {e}')

# Send hangup
url = 'http://localhost:8123/hangup?slot=1'
req = urllib.request.Request(url, method='POST', data=b'')
try:
    resp = urllib.request.urlopen(req, timeout=5)
    print(f'Hangup response: {resp.status} {resp.read().decode()}')
except Exception as e:
    print(f'Hangup failed: {e}')
