#!/usr/bin/env python3
"""Debug why LIVI wireless AA AP isn't starting."""
import subprocess, os, time

# Check wlan1 exists and its state
print('=== wlan1 interface ===')
r = subprocess.run(['ip', 'link', 'show', 'wlan1'], capture_output=True, text=True, timeout=5)
print(r.stdout)
print(r.stderr)

# Bring wlan1 up manually
print('=== Bringing wlan1 up ===')
r = subprocess.run(['sudo', '-S', 'ip', 'link', 'set', 'wlan1', 'up'],
                   input='pi\n', capture_output=True, text=True, timeout=5)
print(f'  rc={r.returncode}, {r.stderr.strip() or "OK"}')
time.sleep(2)

# Check state again
r = subprocess.run(['ip', 'link', 'show', 'wlan1'], capture_output=True, text=True, timeout=5)
print(r.stdout)

# Check iw dev
print('=== iw dev (using full path) ===')
r = subprocess.run(['/usr/sbin/iw', 'dev'], capture_output=True, text=True, timeout=5)
print(r.stdout)

# Check wlan1 capabilities (AP mode?)
print('=== iw phy (AP mode check) ===')
r = subprocess.run(['/usr/sbin/iw', 'phy'], capture_output=True, text=True, timeout=5)
# Look for AP support in the output
output = r.stdout
# Find "Supported interface modes" section
in_modes = False
for line in output.split('\n'):
    if 'Supported interface modes' in line:
        in_modes = True
    elif in_modes and line.strip().startswith('*'):
        print(f'  {line.strip()}')
    elif in_modes and not line.strip().startswith('*'):
        in_modes = False
        break

# Check rfkill
print()
print('=== rfkill ===')
r = subprocess.run(['/usr/sbin/rfkill', 'list'], capture_output=True, text=True, timeout=5)
print(r.stdout)

# Check LIVI logs — try multiple locations
print()
print('=== LIVI logs ===')
log_paths = [
    '/home/raspberry/LIVI/LIVI.log',
    '/home/raspberry/.local/share/LIVI/LIVI.log',
    '/home/raspberry/.config/LIVI/LIVI.log',
]
for path in log_paths:
    if os.path.exists(path):
        print(f'  Found: {path}')
        with open(path) as f:
            lines = f.readlines()[-50:]
        for line in lines:
            print(f'  {line.rstrip()}')
        break
else:
    print('  No LIVI.log found in common locations')
    # Search for it
    r = subprocess.run(['find', '/home/raspberry', '-name', 'LIVI.log', '-o', '-name', 'livi.log', '-o', '-name', '*.log'],
                       capture_output=True, text=True, timeout=10)
    print(f'  Search results: {r.stdout[:500]}')

# journalctl for LIVI
print()
print('=== journalctl LIVI (last 50 lines) ===')
r = subprocess.run(['journalctl', '--user', '-u', 'livi.service', '-n', '50', '--no-pager'],
                   capture_output=True, text=True, timeout=5)
for line in r.stdout.split('\n')[-30:]:
    print(f'  {line}')

# Check if LIVI process is running and its cmdline
print()
print('=== LIVI process ===')
r = subprocess.run(['pgrep', '-a', '-f', 'LIVI'], capture_output=True, text=True, timeout=5)
print(r.stdout)

# Check hostapd config files
print('=== hostapd config ===')
r = subprocess.run(['find', '/home/raspberry', '-name', 'hostapd*', '-type', 'f'],
                   capture_output=True, text=True, timeout=5)
print(f'  hostapd configs: {r.stdout.strip() or "none found"}')

# Check if LIVI created any temp hostapd config
r = subprocess.run(['find', '/tmp', '-name', 'hostapd*', '-type', 'f'],
                   capture_output=True, text=True, timeout=5)
print(f'  /tmp hostapd: {r.stdout.strip() or "none"}')

# Check dmesg for wlan1 errors
print()
print('=== dmesg wlan1 (recent) ===')
r = subprocess.run(['sudo', '-S', 'dmesg'], input='pi\n',
                   capture_output=True, text=True, timeout=5)
for line in r.stdout.split('\n'):
    if 'wlan1' in line or 'rtw88' in line or '8821' in line:
        print(f'  {line.strip()}')
