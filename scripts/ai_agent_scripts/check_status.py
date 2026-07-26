#!/usr/bin/env python3
"""Check sidecar status and weather for debugging."""
import urllib.request, json

# Status
resp = urllib.request.urlopen('http://localhost:8123/status', timeout=5)
status = json.loads(resp.read().decode())
print('STATUS:', json.dumps(status, indent=2))

# Weather
resp = urllib.request.urlopen('http://localhost:8123/weather', timeout=10)
weather = json.loads(resp.read().decode())
current = weather.get('current', {})
print('WEATHER current:', json.dumps(current, indent=2))
