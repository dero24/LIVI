#!/usr/bin/env python3
"""Install iw and rfkill using sudo password 'pi'."""
import subprocess

# Install iw and rfkill
print('=== Installing iw and rfkill ===')
r = subprocess.run(['sudo', '-S', 'apt', 'install', '-y', 'iw', 'rfkill'],
                   input='pi\n', capture_output=True, text=True, timeout=120)
print(f'  exit code: {r.returncode}')
lines = (r.stdout + r.stderr).strip().split('\n')
for line in lines[-15:]:
    print(f'  {line}')

# Verify
print()
print('=== Verification ===')
for pkg in ['iw', 'rfkill']:
    r = subprocess.run(['which', pkg], capture_output=True, text=True, timeout=5)
    print(f'  {pkg}: {r.stdout.strip() or "NOT FOUND"}')

# Test iw can see interfaces
print()
print('=== iw dev ===')
r = subprocess.run(['iw', 'dev'], capture_output=True, text=True, timeout=5)
print(r.stdout)

# rfkill list
print('=== rfkill list ===')
r = subprocess.run(['rfkill', 'list'], capture_output=True, text=True, timeout=5)
print(r.stdout)
