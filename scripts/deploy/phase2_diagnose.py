#!/usr/bin/env python3
"""Phase 2: Diagnose wlan0 drops, check undervoltage, pull logs."""
import subprocess, os

SUDO_PWD = 'pi\n'
def sudo(cmd, timeout=15):
    return subprocess.run(['sudo', '-S'] + cmd, input=SUDO_PWD,
                         capture_output=True, text=True, timeout=timeout)

# 1. Check undervoltage
print('=== 1. Undervoltage check ===')
r = sudo(['vcgencmd', 'get_throttled'], timeout=5)
print(f'  get_throttled: {r.stdout.strip()}')
# Decode the bitmask
try:
    val = int(r.stdout.strip().replace('get_throttled=', ''), 0)
    bits = []
    if val & 0x1: bits.append('under-voltage NOW')
    if val & 0x2: bits.append('arm freq capped NOW')
    if val & 0x4: bits.append('throttled NOW')
    if val & 0x8: bits.append('temp limit NOW')
    if val & 0x10000: bits.append('under-voltage HAS happened')
    if val & 0x20000: bits.append('arm freq capped HAS happened')
    if val & 0x40000: bits.append('throttled HAS happened')
    if val & 0x80000: bits.append('temp limit HAS happened')
    print(f'  Decoded: {", ".join(bits) if bits else "none"}')
except:
    print(f'  Could not decode')

# 2. wlan0 link quality
print()
print('=== 2. wlan0 link quality ===')
r = subprocess.run(['/usr/sbin/iw', 'dev', 'wlan0', 'link'],
                   capture_output=True, text=True, timeout=5)
print(r.stdout)

# 3. wlan0 station dump
print('=== 3. wlan0 station dump ===')
r = subprocess.run(['/usr/sbin/iw', 'dev', 'wlan0', 'station', 'dump'],
                   capture_output=True, text=True, timeout=5)
print(r.stdout[:500])

# 4. WiFi scan (signal strength of connected AP)
print('=== 4. WiFi scan ===')
r = subprocess.run(['nmcli', '-f', 'IN-USE,SSID,SIGNAL,CHAN,FREQ,BARS', 'dev', 'wifi', 'list'],
                   capture_output=True, text=True, timeout=15)
print(r.stdout)

# 5. Apply power_save off to live wlan0 connection
print('=== 5. Apply wlan0 power_save off (live) ===')
r = subprocess.run(['nmcli', 'device', 'modify', 'wlan0', '802-11-wireless.powersave', '2'],
                   capture_output=True, text=True, timeout=10)
print(f'  nmcli modify: rc={r.returncode}, {r.stderr.strip() or "OK"}')
r = sudo(['/usr/sbin/iw', 'dev', 'wlan0', 'set', 'power_save', 'off'], timeout=5)
print(f'  iw power_save off: rc={r.returncode}')
r = subprocess.run(['/usr/sbin/iw', 'dev', 'wlan0', 'get', 'power_save'],
                   capture_output=True, text=True, timeout=5)
print(f'  wlan0 power_save: {r.stdout.strip()}')

# 6. Check rtw88 stability config
print()
print('=== 6. rtw88 stability config ===')
if os.path.exists('/etc/modprobe.d/rtw88-stability.conf'):
    with open('/etc/modprobe.d/rtw88-stability.conf') as f:
        print(f'  Config: {f.read().strip()}')
else:
    print('  NOT FOUND')
# Check if module is loaded
r = subprocess.run(['lsmod'], capture_output=True, text=True, timeout=5)
rtw = [l for l in r.stdout.split('\n') if 'rtw88' in l]
print(f'  Loaded modules: {rtw if rtw else "none (dongle not plugged in)"}')
if rtw:
    r = subprocess.run(['cat', '/sys/module/rtw88_core/parameters/disable_lps_deep'],
                       capture_output=True, text=True, timeout=5)
    print(f'  disable_lps_deep: {r.stdout.strip()}')

# 7. Check sudoers fix
print()
print('=== 7. Sudoers fix ===')
r = sudo(['cat', '/etc/sudoers.d/99-LIVI-bt'], timeout=5)
print(f'  Content: {r.stdout.strip()}')
r = sudo(['visudo', '-c'], timeout=5)
print(f'  visudo check: {r.stdout.strip()}')

# 8. Pull persistent journald logs from previous boot
print()
print('=== 8. Previous boot logs (wlan0/BT/hung/throttle) ===')
r = sudo(['journalctl', '-b', '-1', '--no-pager', '-q'], timeout=15)
if r.stdout:
    lines = r.stdout.split('\n')
    relevant = [l for l in lines if any(x in l.lower() for x in 
        ['brcmfmac', 'wpa_supplicant', 'networkmanager', 'dhcp', 'wlan0', 
         'rtw', 'hung', 'throttl', 'under-voltage', 'bt-autoconnect', 
         'bluetooth-agent', 'livi-helper', 'hostapd'])]
    print(f'  Total lines in -b -1: {len(lines)}')
    print(f'  Relevant lines: {len(relevant)}')
    for line in relevant[-30:]:
        print(f'  {line.strip()[:150]}')
else:
    print('  No previous boot logs (persistent journald may not have been active)')

# 9. Check current boot logs for issues
print()
print('=== 9. Current boot logs (issues) ===')
r = sudo(['journalctl', '-b', '0', '--no-pager', '-q', '-p', 'err'], timeout=10)
for line in r.stdout.split('\n')[-20:]:
    print(f'  {line.strip()[:150]}')

# 10. Check NetworkManager config
print()
print('=== 10. NM power-save config ===')
if os.path.exists('/etc/NetworkManager/conf.d/zz-wifi-powersave-off.conf'):
    with open('/etc/NetworkManager/conf.d/zz-wifi-powersave-off.conf') as f:
        print(f'  Config: {f.read().strip()}')
else:
    print('  NOT FOUND')

# 11. Check if rogue service files still exist (should be disabled but files remain)
print()
print('=== 11. Rogue service files ===')
for svc in ['bluetooth-agent.service', 'bt-autoconnect.service']:
    path = f'/home/raspberry/.config/systemd/user/{svc}'
    if os.path.exists(path):
        print(f'  {svc}: EXISTS (disabled)')
        # Also check for the scripts they run
    else:
        print(f'  {svc}: not found')

# Check for bt-agent.py and bt_autoconnect.py
for script in ['bt-agent.py', 'bt_autoconnect.py']:
    path = f'/home/raspberry/{script}'
    if os.path.exists(path):
        print(f'  {script}: EXISTS at {path}')
    else:
        print(f'  {script}: not found')
