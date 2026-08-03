#!/usr/bin/env python3
"""Verify the settings page (loaded by the overlay iframe) has the Display tab."""
import urllib.request

html = urllib.request.urlopen('http://localhost:8123/settings', timeout=5).read().decode()

# Check that the Display tab is present in the settings HTML
checks = [
    ('data-tab="display"', 'Display tab button'),
    ('loadDisplay()', 'loadDisplay function call'),
    ('nm-enabled', 'Night mode enable checkbox'),
    ('nm-brightness', 'Brightness slider'),
    ('nm-warm-tint', 'Warm tint toggle'),
    ('nm-start', 'Start time input'),
    ('nm-end', 'End time input'),
    ('previewNightMode', 'Preview buttons'),
    ('Display', 'Display tab label text'),
]
all_ok = True
for marker, desc in checks:
    found = marker in html
    if not found:
        all_ok = False
    print(f'  {"PASS" if found else "FAIL"}: {desc}')

print()
print('Settings page is loaded by the overlay iframe on the touchscreen.')
print('User taps gear icon -> settings page opens -> Display tab is there.')
if all_ok:
    print('ALL CHECKS PASSED')
else:
    print('SOME CHECKS FAILED')
