#!/usr/bin/env python3
"""Check if the LIVI helper process received LIVI_AA_WIRELESS=1."""
import subprocess, os

# Get the helper PID
r = subprocess.run(['pgrep', '-f', 'livi-helper'], capture_output=True, text=True, timeout=5)
pids = r.stdout.strip().split('\n')
print(f'Helper PIDs: {pids}')

for pid in pids:
    if not pid:
        continue
    # Read the environment of the process
    try:
        with open(f'/proc/{pid}/environ', 'rb') as f:
            env_data = f.read().decode('utf-8', errors='replace')
        env_vars = env_data.split('\x00')
        print(f'\n=== PID {pid} environment (LIVI-related) ===')
        for var in env_vars:
            if 'LIVI' in var or 'WIFI' in var or 'WIRELESS' in var or 'AA' in var or 'BT' in var:
                print(f'  {var}')
        # Also check all env vars for completeness
        print(f'  (total env vars: {len([v for v in env_vars if v])})')
    except PermissionError:
        print(f'  PID {pid}: permission denied (need sudo)')
        r = subprocess.run(['sudo', '-S', 'cat', f'/proc/{pid}/environ'],
                          input='pi\n', capture_output=True, text=True, timeout=5)
        env_data = r.stdout
        env_vars = env_data.split('\x00')
        print(f'\n=== PID {pid} environment (LIVI-related) ===')
        for var in env_vars:
            if 'LIVI' in var or 'WIFI' in var or 'WIRELESS' in var or 'AA' in var or 'BT' in var:
                print(f'  {var}')
        print(f'  (total env vars: {len([v for v in env_vars if v])})')

# Also check the main livi process
r = subprocess.run(['pgrep', '-f', 'livi --ozone'], capture_output=True, text=True, timeout=5)
livi_pids = r.stdout.strip().split('\n')
print(f'\nLIVI main PIDs: {livi_pids}')
for pid in livi_pids[:1]:  # Just check the first one
    if not pid:
        continue
    r = subprocess.run(['sudo', '-S', 'cat', f'/proc/{pid}/environ'],
                      input='pi\n', capture_output=True, text=True, timeout=5)
    env_vars = r.stdout.split('\x00')
    print(f'=== PID {pid} environment (LIVI-related) ===')
    for var in env_vars:
        if 'LIVI' in var or 'WIFI' in var or 'WIRELESS' in var or 'AA' in var:
            print(f'  {var}')

# Check the compositor
r = subprocess.run(['pgrep', '-f', 'livi-compositor'], capture_output=True, text=True, timeout=5)
comp_pids = r.stdout.strip().split('\n')
print(f'\nCompositor PIDs: {comp_pids}')
for pid in comp_pids[:1]:
    if not pid:
        continue
    r = subprocess.run(['sudo', '-S', 'cat', f'/proc/{pid}/environ'],
                      input='pi\n', capture_output=True, text=True, timeout=5)
    env_vars = r.stdout.split('\x00')
    print(f'=== PID {pid} environment (LIVI-related) ===')
    for var in env_vars:
        if 'LIVI' in var or 'WIFI' in var or 'WIRELESS' in var or 'AA' in var:
            print(f'  {var}')

# Also search the asar more carefully for how wirelessAaEnabled is used
print()
print('=== Searching asar for wirelessAaEnabled usage ===')
r = subprocess.run(['strings', '/home/raspberry/LIVI/extracted/resources/app.asar'],
                   capture_output=True, text=True, timeout=10)
for line in r.stdout.split('\n'):
    if 'wirelessAaEnabled' in line or 'wirelessAa' in line:
        print(f'  {line[:200]}')
