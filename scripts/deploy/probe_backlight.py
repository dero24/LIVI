#!/usr/bin/env python3
"""Probe backlight hardware on the Pi."""
import os, glob, subprocess

print('=== /sys/class/backlight/ entries ===')
backlights = glob.glob('/sys/class/backlight/*/')
if not backlights:
    print('  (none found)')
for path in backlights:
    print(f'\n  PATH: {path}')
    for attr in ['max_brightness', 'brightness', 'actual_brightness', 'bl_power']:
        try:
            with open(os.path.join(path, attr)) as f:
                print(f'    {attr}: {f.read().strip()}')
        except Exception as e:
            print(f'    {attr}: ERROR ({e})')

print('\n=== Display info ===')
try:
    r = subprocess.run(['wlr-randr'], capture_output=True, text=True, timeout=5)
    print(r.stdout[:500])
except Exception as e:
    print(f'  wlr-randr: {e}')

# Check if brightnessctl is available
print('\n=== brightnessctl ===')
try:
    r = subprocess.run(['brightnessctl', '--list'], capture_output=True, text=True, timeout=5)
    print(r.stdout[:500])
except FileNotFoundError:
    print('  brightnessctl not installed')
except Exception as e:
    print(f'  brightnessctl: {e}')

# Check current user's groups (need 'video' group for backlight access)
print('\n=== User groups ===')
try:
    r = subprocess.run(['groups'], capture_output=True, text=True, timeout=5)
    print(f'  {r.stdout.strip()}')
except Exception as e:
    print(f'  {e}')

print('\n=== Permissions on backlight brightness ===')
for path in backlights:
    try:
        r = subprocess.run(['ls', '-la', os.path.join(path, 'brightness')], capture_output=True, text=True, timeout=5)
        print(f'  {r.stdout.strip()}')
    except Exception as e:
        print(f'  {e}')
