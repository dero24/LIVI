#!/usr/bin/env python3
"""Fix autosuspend for Pi 5 and restart LIVI to bring up AP."""
import subprocess, os, time

SUDO_PWD = 'pi\n'
def sudo_run(cmd, timeout=30):
    return subprocess.run(['sudo', '-S'] + cmd, input=SUDO_PWD,
                         capture_output=True, text=True, timeout=timeout)

# 1. Check ALL boot config files
print('=== Boot config files ===')
for path in ['/boot/firmware/cmdline.txt', '/boot/cmdline.txt']:
    if os.path.exists(path):
        r = sudo_run(['cat', path], timeout=5)
        print(f'  {path}: {r.stdout.strip()[:200]}')

# Check if there's a config.txt that might override
print()
for path in ['/boot/firmware/config.txt', '/boot/config.txt']:
    if os.path.exists(path):
        r = sudo_run(['cat', path], timeout=5)
        print(f'  {path}:')
        for line in r.stdout.split('\n'):
            if 'cmdline' in line.lower() or 'usb' in line.lower() or 'autosuspend' in line.lower():
                print(f'    {line}')

# 2. The Pi 5 may use /boot/firmware/cmdline.txt but with a different format
# Let's check what the actual file looks like and re-apply
print()
print('=== Re-applying autosuspend fix ===')
cmdline_path = '/boot/firmware/cmdline.txt'
r = sudo_run(['cat', cmdline_path], timeout=5)
cmdline = r.stdout.strip()
print(f'  Current: {cmdline[:150]}...')

if 'usbcore.autosuspend=-1' not in cmdline:
    new_cmdline = cmdline + ' usbcore.autosuspend=-1'
    r = sudo_run(['bash', '-c', f'echo -n "{new_cmdline}" > {cmdline_path}'], timeout=5)
    print(f'  Write rc: {r.returncode}')
    r = sudo_run(['cat', cmdline_path], timeout=5)
    print(f'  Verified: {r.stdout.strip()[:200]}...')
    # Also check if there's a backup mechanism
    r = sudo_run(['ls', '-la', '/boot/firmware/'], timeout=5)
    print(f'  Firmware dir:')
    for line in r.stdout.split('\n'):
        if 'cmdline' in line or 'config' in line:
            print(f'    {line}')
else:
    print('  Already present in file')

# 3. Check if the Pi 5 uses tryboot or something else
print()
print('=== Pi 5 boot EEPROM ===')
r = sudo_run(['rpi-eeprom-update'], timeout=10)
print(r.stdout[:300])

# 4. For NOW - disable autosuspend at runtime via sysfs
print()
print('=== Disabling autosuspend at runtime ===')
# Set autosuspend to -1 (disabled) via module param
r = sudo_run(['bash', '-c', 'echo -1 > /sys/module/usbcore/parameters/autosuspend'], timeout=5)
print(f'  Set autosuspend=-1: rc={r.returncode}')
r = subprocess.run(['cat', '/sys/module/usbcore/parameters/autosuspend'],
                   capture_output=True, text=True, timeout=5)
print(f'  Verified: {r.stdout.strip()}')

# 5. Also set all USB devices to always on
print()
print('=== Setting all USB devices to always on ===')
r = subprocess.run(['find', '/sys/bus/usb/devices', '-name', 'control', '-path', '*/power/*'],
                   capture_output=True, text=True, timeout=5)
for cp in r.stdout.strip().split('\n'):
    if cp:
        r2 = sudo_run(['bash', '-c', f'echo on > {cp}'], timeout=5)
        with open(cp) as f:
            val = f.read().strip()
        dev = cp.split('/power/')[0].split('/')[-1]
        if val != 'on':
            print(f'  {dev}: {val} (FAILED to set on)')
        # Only print non-on ones

# 6. Disable wlan0 power_save
print()
print('=== wlan0 power_save ===')
r = sudo_run(['/usr/sbin/iw', 'dev', 'wlan0', 'set', 'power_save', 'off'], timeout=5)
print(f'  rc={r.returncode}')

# 7. Bring wlan1 up and restart LIVI
print()
print('=== Bringing wlan1 up ===')
r = sudo_run(['ip', 'link', 'set', 'wlan1', 'up'], timeout=5)
print(f'  rc={r.returncode}')
time.sleep(3)

r = subprocess.run(['ip', 'link', 'show', 'wlan1'], capture_output=True, text=True, timeout=5)
print(f'  State: {r.stdout.strip()}')

# 8. Restart LIVI
print()
print('=== Restarting LIVI ===')
r = subprocess.run(['systemctl', '--user', 'restart', 'livi.service'],
                   capture_output=True, text=True, timeout=10)
print(f'  rc={r.returncode}')

print('  Waiting 20s for AP to come up...')
time.sleep(20)

# 9. Check AP status
print()
print('=== AP status ===')
r = subprocess.run(['pgrep', '-a', 'hostapd'], capture_output=True, text=True, timeout=5)
print(f'  hostapd: {r.stdout.strip() or "not running"}')

r = subprocess.run(['pgrep', '-a', 'dnsmasq'], capture_output=True, text=True, timeout=5)
print(f'  dnsmasq: {r.stdout.strip() or "not running"}')

r = subprocess.run(['ip', 'addr', 'show', 'wlan1'], capture_output=True, text=True, timeout=5)
for line in r.stdout.split('\n'):
    if 'state' in line or 'inet ' in line:
        print(f'  wlan1: {line.strip()}')

if os.path.exists('/tmp/livi-hostapd.conf'):
    print('  hostapd config: EXISTS')
else:
    print('  hostapd config: not found')

# 10. Check helper env
r = subprocess.run(['pgrep', '-f', 'livi-helper'], capture_output=True, text=True, timeout=5)
pids = r.stdout.strip().split('\n')
for pid in pids:
    if not pid: continue
    r2 = sudo_run(['cat', f'/proc/{pid}/environ'], timeout=5)
    has_wireless = 'LIVI_AA_WIRELESS=1' in r2.stdout
    print(f'  Helper PID {pid}: LIVI_AA_WIRELESS=1 = {has_wireless}')
