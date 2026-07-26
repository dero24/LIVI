#!/usr/bin/env python3
"""Verify deployed code by searching the ASAR binary for our markers."""
import subprocess

asar_path = '/home/raspberry/LIVI/extracted/resources/app.asar'

markers = [
    ('padding: 16px 44px', 'bubble padding 44px', True),
    ('HUB_HEIGHT = 445', 'hub height 445', True),
    ('inline-flex', 'inline-flex bubble', True),
    ('padding-right: 8px', 'text padding-right 8px', True),
    ('border-radius: 26px', 'border radius 26px', True),
    ('background:#0d1117', 'pure dark bg (no gradient)', True),
    ('font-size: 72px', 'clock 72px (was 64px)', True),
    ('font-weight: 200', 'thin clock weight 200', True),
    ('padding: 36px 40px 0', 'header padding 36px/40px', True),
    ('font-weight: 300', 'light weight 300 (screensaver style)', True),
    ('background: transparent', 'now-playing no card', True),
    ('showRegistrationPrompt', 'registration prompt', True),
    ('hub-kb-key', 'touch keyboard', True),
    ('createRingBanner', 'floating ring banner', True),
    ('handleActiveDevice', 'registration gating', True),
    ("sendCmd('pause')", 'music auto-pause', True),
    # Old values that should be gone
    ('padding: 14px 32px', 'OLD padding 32px (should be gone)', False),
    ('HUB_HEIGHT = 440', 'OLD hub height 440 (should be gone)', False),
    ('HUB_HEIGHT = 424', 'OLD hub height 424 (should be gone)', False),
    ('linear-gradient(180deg,#0d1117', 'OLD gradient bg (should be gone)', False),
    ('font-size: 64px', 'OLD clock 64px (should be gone)', False),
    ('Connected Phones', 'OLD devices label (should be gone)', False),
    ('background: rgba(255,255,255,0.04)', 'OLD now-playing card bg (should be gone)', False),
]

for needle, label, should_exist in markers:
    result = subprocess.run(
        ['grep', '-c', needle, asar_path],
        capture_output=True, text=True
    )
    count = int(result.stdout.strip()) if result.stdout.strip().isdigit() else 0
    if should_exist:
        status = 'OK' if count > 0 else 'MISSING'
    else:
        status = 'OK (gone)' if count == 0 else 'STILL EXISTS'
    print(f'{status:15s}  {label}  (count={count})')
