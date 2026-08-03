#!/usr/bin/env python3
"""EMERGENCY: Disable USB autosuspend + create persistent boot fix.
Run this IMMEDIATELY after Pi boots to prevent hang."""
import subprocess, time, os, sys

SUDO_PWD = 'pi\n'
def sudo(cmd, timeout=10):
    return subprocess.run(['sudo', '-S'] + cmd, input=SUDO_PWD,
                         capture_output=True, text=True, timeout=timeout)

# 1. IMMEDIATE: Disable autosuspend at runtime
print('=== 1. Disable USB autosuspend NOW ===')
r = sudo(['bash', '-c', 'echo -1 > /sys/module/usbcore/parameters/autosuspend'], timeout=5)
r2 = subprocess.run(['cat', '/sys/module/usbcore/parameters/autosuspend'],
                    capture_output=True, text=True, timeout=3)
print(f'  autosuspend = {r2.stdout.strip()} (should be -1)')

# 2. IMMEDIATE: Set ALL USB devices to always-on
print('=== 2. Set all USB devices to always-on ===')
r = subprocess.run(['find', '/sys/bus/usb/devices', '-name', 'control', '-path', '*/power/*'],
                   capture_output=True, text=True, timeout=5)
count = 0
for cp in r.stdout.strip().split('\n'):
    if cp:
        sudo(['bash', '-c', f'echo on > {cp}'], timeout=3)
        count += 1
print(f'  Set {count} USB devices to always-on')

# 3. IMMEDIATE: Disable wlan0 power_save
print('=== 3. Disable wlan0 power_save ===')
sudo(['/usr/sbin/iw', 'dev', 'wlan0', 'set', 'power_save', 'off'], timeout=5)
r = subprocess.run(['/usr/sbin/iw', 'dev', 'wlan0', 'get', 'power_save'],
                   capture_output=True, text=True, timeout=3)
print(f'  wlan0 power_save: {r.stdout.strip()}')

# 4. PERSISTENT: Create systemd service that runs on every boot
print('=== 4. Create persistent boot service ===')
service = """[Unit]
Description=Disable USB autosuspend (prevent WiFi dongle hang)
Before=livi.service
DefaultDependencies=no

[Service]
Type=oneshot
ExecStart=/bin/bash -c 'echo -1 > /sys/module/usbcore/parameters/autosuspend; for f in /sys/bus/usb/devices/*/power/control; do echo on > "$f" 2>/dev/null; done; /usr/sbin/iw dev wlan0 set power_save off 2>/dev/null; true'
RemainAfterExit=yes

[Install]
WantedBy=sysinit.target
"""
service_path = '/etc/systemd/system/usb-autosuspend-fix.service'
sudo(['bash', '-c', f"cat > {service_path} << 'ENDFILE'\n{service}ENDFILE"], timeout=5)
sudo(['systemctl', 'daemon-reload'], timeout=5)
sudo(['systemctl', 'enable', 'usb-autosuspend-fix.service'], timeout=5)
r = sudo(['systemctl', 'is-enabled', 'usb-autosuspend-fix.service'], timeout=5)
print(f'  Service enabled: {r.stdout.strip()}')

# 5. ALSO PERSISTENT: udev rule for the dongle specifically
print('=== 5. udev rule for dongle ===')
udev = 'ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="2357", ATTR{idProduct}=="011e", TEST=="power/control", ATTR{power/control}="on"\n'
sudo(['bash', '-c', f"echo -n '{udev}' > /etc/udev/rules.d/99-usb-dongle-power.rules"], timeout=5)
sudo(['udevadm', 'control', '--reload-rules'], timeout=5)
print('  udev rule installed')

# 6. CHECK: Is the kernel param actually in /proc/cmdline?
print('=== 6. Check kernel param ===')
r = subprocess.run(['cat', '/proc/cmdline'], capture_output=True, text=True, timeout=3)
cmdline = r.stdout.strip()
has_param = 'usbcore.autosuspend=-1' in cmdline
print(f'  usbcore.autosuspend=-1 in /proc/cmdline: {has_param}')
if not has_param:
    print('  WARNING: Kernel param NOT active! The boot service above will handle it.')
    # Also try adding to modprobe config as fallback
    sudo(['bash', '-c', 'echo "options usbcore autosuspend=-1" > /etc/modprobe.d/usb-autosuspend.conf'], timeout=5)
    print('  Added modprobe.d fallback config')

# 7. Verify dongle is present and working
print('=== 7. Dongle status ===')
r = subprocess.run(['lsusb'], capture_output=True, text=True, timeout=5)
for line in r.stdout.split('\n'):
    if '2357' in line or 'TP-Link' in line or 'Realtek' in line:
        print(f'  {line.strip()}')
r = subprocess.run(['ip', 'link', 'show', 'wlan1'], capture_output=True, text=True, timeout=3)
print(f'  wlan1: {r.stdout.strip()[:80]}')

# 8. Check LIVI and sidecar
print('=== 8. Services ===')
for svc in ['livi.service', 'homephone-sidecar.service']:
    r = subprocess.run(['systemctl', '--user', 'is-active', svc],
                       capture_output=True, text=True, timeout=3)
    print(f'  {svc}: {r.stdout.strip()}')

print()
print('=== DONE ===')
print('USB autosuspend disabled. Boot service created and enabled.')
print('The Pi should NOT hang when idle now.')
print('If it still hangs, the issue may be the rtw88 driver itself,')
print('not just autosuspend — we may need a powered USB hub.')
