#!/usr/bin/env python3
"""Check kernel version, firmware status, and LIVI's actual log output."""
import subprocess, os, glob

# Kernel version
print('=== Kernel version ===')
r = subprocess.run(['uname', '-r'], capture_output=True, text=True, timeout=5)
print(f'  {r.stdout.strip()}')

# Check if wlan1 is actually functional now
print()
print('=== wlan1 current state ===')
r = subprocess.run(['/usr/sbin/iw', 'dev', 'wlan1', 'info'], capture_output=True, text=True, timeout=5)
print(r.stdout if r.stdout else f'  Error: {r.stderr.strip()}')

# Check if firmware loaded successfully (latest dmesg)
print()
print('=== Recent dmesg for rtw88 (last 10) ===')
r = subprocess.run(['sudo', '-S', 'dmesg'], input='pi\n',
                   capture_output=True, text=True, timeout=5)
rtw_lines = [l for l in r.stdout.split('\n') if 'rtw88' in l or 'wlan1' in l]
for line in rtw_lines[-10:]:
    print(f'  {line.strip()}')

# Check firmware files
print()
print('=== Firmware files for rtw88 ===')
r = subprocess.run(['find', '/lib/firmware', '-name', 'rtw88*'], capture_output=True, text=True, timeout=5)
print(r.stdout.strip() or '  none found')

# LIVI service stdout/stderr
print()
print('=== LIVI service logs ===')
# Check systemd service file to see where output goes
r = subprocess.run(['cat', '/home/raspberry/.config/systemd/user/livi.service'],
                   capture_output=True, text=True, timeout=5)
print('  Service file:')
print(r.stdout)

# Check for any log files LIVI might write
print()
print('=== Looking for LIVI logs ===')
r = subprocess.run(['find', '/home/raspberry', '-name', '*.log', '-newer', '/home/raspberry/.config/LIVI/config.json'],
                   capture_output=True, text=True, timeout=10)
print(f'  Recent log files: {r.stdout.strip() or "none"}')

# Check the LIVI helper script for wireless AA handling
print()
print('=== LIVI helper script (wireless AA related) ===')
helper_path = '/home/raspberry/LIVI/extracted/resources/driver/helper/livi-helper.py'
if os.path.exists(helper_path):
    r = subprocess.run(['grep', '-n', '-i', 'wireless\|wlan\|hostapd\|wifi\|hotspot\|ap_mode\|wirelessAa'],
                       input='', capture_output=True, text=True, timeout=5)
    # Actually read the file and search
    with open(helper_path) as f:
        lines = f.readlines()
    for i, line in enumerate(lines, 1):
        if any(x in line.lower() for x in ['wireless', 'wlan', 'hostapd', 'wifi', 'hotspot', 'ap_mode', 'wirelessaa', 'aa_wireless']):
            print(f'  {i}: {line.rstrip()}')
else:
    print(f'  Helper not found at {helper_path}')

# Check if LIVI asar has wireless AA code
print()
print('=== LIVI asar - wireless AA references ===')
r = subprocess.run(['grep', '-c', 'wirelessAa', '/home/raspberry/LIVI/extracted/resources/app.asar'],
                   capture_output=True, text=True, timeout=5)
print(f'  wirelessAa occurrences in asar: {r.stdout.strip()}')

# Try to extract relevant strings from asar
r = subprocess.run(['strings', '/home/raspberry/LIVI/extracted/resources/app.asar'],
                   capture_output=True, text=True, timeout=10)
aa_lines = [l for l in r.stdout.split('\n') if 'wirelessAa' in l or 'wifiInterface' in l or 'hostapd' in l]
for line in aa_lines[:10]:
    print(f'  {line[:120]}')

# Check USB power
print()
print('=== USB power/current ===')
r = subprocess.run(['sudo', '-S', 'bash', '-c', 'cat /sys/bus/usb/devices/3-1/bMaxPower 2>/dev/null; echo; cat /sys/bus/usb/devices/3-1/maxchild 2>/dev/null'],
                   input='pi\n', capture_output=True, text=True, timeout=5)
print(f'  {r.stdout.strip()}')
