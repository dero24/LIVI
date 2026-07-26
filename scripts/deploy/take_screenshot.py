#!/usr/bin/env python3
"""Take a screenshot from LIVI's nested compositor (wayland-1)."""
import subprocess, os, time

time.sleep(1)

env = os.environ.copy()
env['WAYLAND_DISPLAY'] = 'wayland-1'
env['XDG_RUNTIME_DIR'] = '/run/user/1000'
result = subprocess.run(['grim', '/tmp/homehub_screenshot.png'], env=env, capture_output=True, text=True)
print(f'Screenshot wayland-1: {result.returncode} {result.stderr.strip()}')

if os.path.exists('/tmp/homehub_screenshot.png'):
    print(f'Size: {os.path.getsize("/tmp/homehub_screenshot.png")} bytes')
else:
    # Try wayland-0
    env['WAYLAND_DISPLAY'] = 'wayland-0'
    result = subprocess.run(['grim', '/tmp/homehub_screenshot0.png'], env=env, capture_output=True, text=True)
    print(f'Screenshot wayland-0: {result.returncode} {result.stderr.strip()}')
    if os.path.exists('/tmp/homehub_screenshot0.png'):
        print(f'Size wayland-0: {os.path.getsize("/tmp/homehub_screenshot0.png")} bytes')
