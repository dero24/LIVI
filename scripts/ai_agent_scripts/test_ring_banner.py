#!/usr/bin/env python3
"""Send a test ring, take screenshot with correct env, then hangup."""
import urllib.request
import time
import subprocess
import os

# Send ring
url = 'http://localhost:8123/ring?slot=1&caller=John%20Doe&phone=Pixel%208'
req = urllib.request.Request(url, method='POST', data=b'')
resp = urllib.request.urlopen(req, timeout=5)
print(f'Ring sent: {resp.read().decode()}')

# Wait 3 seconds for the banner to appear
time.sleep(3)

# Take screenshot with correct env
env = os.environ.copy()
env['WAYLAND_DISPLAY'] = 'wayland-0'
env['XDG_RUNTIME_DIR'] = '/run/user/1000'
result = subprocess.run(['grim', '/tmp/ring_screenshot.png'], env=env, capture_output=True, text=True)
print(f'Screenshot: {result.returncode} {result.stderr.strip()}')

# Check file
if os.path.exists('/tmp/ring_screenshot.png'):
    print(f'Screenshot size: {os.path.getsize("/tmp/ring_screenshot.png")} bytes')

# Wait 2 more seconds
time.sleep(2)

# Hangup
url = 'http://localhost:8123/hangup?slot=1'
req = urllib.request.Request(url, method='POST', data=b'')
resp = urllib.request.urlopen(req, timeout=5)
print(f'Hangup sent: {resp.read().decode()}')
