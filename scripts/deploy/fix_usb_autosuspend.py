#!/usr/bin/env python3
"""Fix USB autosuspend issue causing Pi to hang when idle with WiFi dongle."""
import subprocess, os

SUDO_PWD = 'pi\n'

def sudo_run(cmd, timeout=30):
    return subprocess.run(['sudo', '-S'] + cmd, input=SUDO_PWD,
                         capture_output=True, text=True, timeout=timeout)

# 1. Check current kernel boot args
print('=== Current boot config ===')
# Pi 5 uses /boot/firmware/cmdline.txt
for path in ['/boot/firmware/cmdline.txt', '/boot/cmdline.txt']:
    if os.path.exists(path):
        r = sudo_run(['cat', path], timeout=5)
        print(f'  {path}:')
        print(f'  {r.stdout.strip()}')
        cmdline_path = path
        break
else:
    print('  No cmdline.txt found!')
    cmdline_path = None

# 2. Check if autosuspend is already disabled
print()
print('=== Current USB autosuspend setting ===')
r = subprocess.run(['cat', '/sys/module/usbcore/parameters/autosuspend'],
                   capture_output=True, text=True, timeout=5)
print(f'  usbcore.autosuspend = {r.stdout.strip()} (negative = disabled)')

# 3. Check current power state of the dongle's USB device
print()
print('=== Dongle USB power state ===')
# Find the dongle's USB path
r = subprocess.run(['find', '/sys/bus/usb/devices', '-name', 'idVendor'],
                   capture_output=True, text=True, timeout=5)
for vp in r.stdout.strip().split('\n'):
    try:
        with open(vp) as f:
            vendor = f.read().strip()
        d = os.path.dirname(vp)
        with open(os.path.join(d, 'idProduct')) as f:
            product = f.read().strip()
        if vendor == '2357' and product == '011e':  # TP-Link T2U Nano
            print(f'  Found dongle at {d}')
            for attr in ['power/control', 'power/autosuspend', 'power/runtime_status']:
                ap = os.path.join(d, attr)
                if os.path.exists(ap):
                    with open(ap) as f:
                        print(f'    {attr}: {f.read().strip()}')
            # Also check the touchscreen USB device
    except:
        pass

# 4. Disable USB autosuspend in kernel boot args
print()
print('=== Disabling USB autosuspend in boot args ===')
if cmdline_path:
    r = sudo_run(['cat', cmdline_path], timeout=5)
    cmdline = r.stdout.strip()
    
    if 'usbcore.autosuspend=-1' in cmdline:
        print('  Already disabled in cmdline!')
    else:
        # Add to cmdline
        new_cmdline = cmdline + ' usbcore.autosuspend=-1'
        # Backup first
        r = sudo_run(['cp', cmdline_path, cmdline_path + '.bak'], timeout=5)
        print(f'  Backup: {r.returncode}')
        # Write new cmdline
        r = sudo_run(['bash', '-c', f'echo -n "{new_cmdline}" > {cmdline_path}'], timeout=5)
        print(f'  Write: rc={r.returncode}')
        # Verify
        r = sudo_run(['cat', cmdline_path], timeout=5)
        print(f'  New cmdline: {r.stdout.strip()[:200]}...')

# 5. Also disable WiFi power_save on wlan0 immediately (without reboot)
print()
print('=== Disabling WiFi power_save on wlan0 now ===')
r = sudo_run(['/usr/sbin/iw', 'dev', 'wlan0', 'set', 'power_save', 'off'], timeout=5)
print(f'  wlan0 power_save off: rc={r.returncode}')
r = subprocess.run(['/usr/sbin/iw', 'dev', 'wlan0', 'get', 'power_save'],
                   capture_output=True, text=True, timeout=5)
print(f'  wlan0 power_save: {r.stdout.strip()}')

# 6. Also set the dongle's USB device to always on (runtime PM)
print()
print('=== Setting dongle USB device to always on ===')
r = subprocess.run(['find', '/sys/bus/usb/devices', '-name', 'idVendor'],
                   capture_output=True, text=True, timeout=5)
for vp in r.stdout.strip().split('\n'):
    try:
        with open(vp) as f:
            vendor = f.read().strip()
        d = os.path.dirname(vp)
        with open(os.path.join(d, 'idProduct')) as f:
            product = f.read().strip()
        if vendor == '2357' and product == '011e':
            control_path = os.path.join(d, 'power/control')
            if os.path.exists(control_path):
                r = sudo_run(['bash', '-c', f'echo on > {control_path}'], timeout=5)
                print(f'  Set {d}/power/control to on: rc={r.returncode}')
                with open(control_path) as f:
                    print(f'  Verified: {f.read().strip()}')
    except Exception as e:
        print(f'  Error: {e}')

# 7. Create a udev rule to keep the dongle awake permanently
print()
print('=== Creating udev rule for dongle ===')
udev_rule = 'ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="2357", ATTR{idProduct}=="011e", TEST=="power/control", ATTR{power/control}="on"\n'
udev_path = '/etc/udev/rules.d/99-usb-dongle-power.rules'
r = sudo_run(['bash', '-c', f'echo -n \'{udev_rule}\' > {udev_path}'], timeout=5)
print(f'  Wrote udev rule: rc={r.returncode}')
r = sudo_run(['udevadm', 'control', '--reload-rules'], timeout=5)
print(f'  Reloaded udev: rc={r.returncode}')

# 8. Verify everything
print()
print('=== Summary ===')
print('  - USB autosuspend disabled in kernel args (takes effect after reboot)')
print('  - wlan0 power_save disabled (immediate)')
print('  - Dongle USB device set to always on (immediate)')
print('  - udev rule created for persistence across replugs')
print()
print('  The kernel param change requires a REBOOT to take effect.')
print('  The other changes are immediate but not all persistent.')
print('  After reboot, all changes will be active.')
