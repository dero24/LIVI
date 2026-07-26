#!/usr/bin/env python3
"""Test mic recording directly."""
import subprocess, os, time

source = 'bluez_input.11:11:11:00:00:00'
tmp = '/tmp/mic_test_raw.wav'
try:
    os.remove(tmp)
except OSError:
    pass

print(f"Recording from {source}...")
proc = subprocess.Popen(
    ['parecord', '--device=' + source, tmp],
    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
)
try:
    proc.wait(timeout=4)
except subprocess.TimeoutExpired:
    proc.kill()
    proc.wait()
    print("Killed after timeout (expected)")

stderr = proc.stderr.read().decode() if proc.stderr else ''
print(f"stderr: {stderr}")
print(f"File exists: {os.path.exists(tmp)}")
if os.path.exists(tmp):
    print(f"File size: {os.path.getsize(tmp)} bytes")
else:
    print("No file produced")
