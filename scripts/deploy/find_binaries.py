#!/usr/bin/env python3
"""Find iw and rfkill binaries — apt says installed but which can't find them."""
import subprocess, glob, os

# dpkg to see where the files are
print('=== dpkg -L iw ===')
r = subprocess.run(['dpkg', '-L', 'iw'], capture_output=True, text=True, timeout=5)
print(r.stdout)

print('=== dpkg -L rfkill ===')
r = subprocess.run(['dpkg', '-L', 'rfkill'], capture_output=True, text=True, timeout=5)
print(r.stdout)

# Search common locations
print('=== File search ===')
for name in ['iw', 'rfkill']:
    found = []
    for path in ['/usr/bin', '/usr/sbin', '/usr/local/bin', '/usr/local/sbin', '/bin', '/sbin']:
        full = os.path.join(path, name)
        if os.path.exists(full):
            found.append(full)
    # Also try find
    if not found:
        r = subprocess.run(['find', '/usr', '-name', name, '-type', 'f'], 
                          capture_output=True, text=True, timeout=10)
        found = [l for l in r.stdout.strip().split('\n') if l]
    print(f'  {name}: {found if found else "NOT FOUND anywhere"}')

# Check PATH
print()
print(f'PATH: {os.environ.get("PATH", "")}')
