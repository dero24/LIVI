#!/usr/bin/env python3
"""Find PhoneStatus handling in the compiled asar."""
import subprocess
import tempfile
import os

ASAR = '/home/raspberry/LIVI/extracted/resources/app.asar'

# Extract the asar to a temp dir using npx asar
tmpdir = '/tmp/asar_extract'
os.makedirs(tmpdir, exist_ok=True)

# Try using the asar binary that comes with LIVI
result = subprocess.run(['npx', 'asar', 'extract', ASAR, tmpdir],
                       capture_output=True, text=True, timeout=60)
print("Extract stdout:", result.stdout[:200])
print("Extract stderr:", result.stderr[:200])

# Search for PhoneStatus in all JS files
for root, dirs, files in os.walk(tmpdir):
    for fname in files:
        if not fname.endswith('.js'):
            continue
        fpath = os.path.join(root, fname)
        try:
            with open(fpath, 'r', errors='ignore') as f:
                content = f.read()
            if 'PhoneStatus' in content or 'PHONE_STATUS' in content or 'phone_status' in content:
                relpath = os.path.relpath(fpath, tmpdir)
                print(f"\n=== Found in {relpath} ({len(content)} bytes) ===")
                # Find the context around PhoneStatus
                idx = 0
                while True:
                    idx = content.find('PhoneStatus', idx)
                    if idx == -1:
                        idx = 0
                        break
                    start = max(0, idx - 100)
                    end = min(len(content), idx + 300)
                    print(f"  ...{content[start:end]}...")
                    print("---")
                    idx += 11
        except:
            pass
