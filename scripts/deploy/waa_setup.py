#!/usr/bin/env python3
"""Steps 2-4: Set wlan1 unmanaged, update LIVI config, restart, verify."""
import subprocess, json, time, os

SUDO_PWD = 'pi\n'

def sudo_run(cmd):
    return subprocess.run(['sudo', '-S'] + cmd, input=SUDO_PWD, 
                         capture_output=True, text=True, timeout=30)

# ===== Step 2: Set wlan1 unmanaged by NetworkManager =====
print('=== Step 2: Set wlan1 unmanaged by NetworkManager ===')

# Method 1: nmcli dev set managed no
r = subprocess.run(['nmcli', 'dev', 'set', 'wlan1', 'managed', 'no'],
                   capture_output=True, text=True, timeout=10)
print(f'  nmcli dev set: rc={r.returncode}, {r.stderr.strip() or "OK"}')

# Method 2: Also add to NetworkManager.conf as backup
nm_conf = '/etc/NetworkManager/NetworkManager.conf'
r = sudo_run(['bash', '-c', 
    'grep -q "wlan1" /etc/NetworkManager/NetworkManager.conf 2>/dev/null && echo EXISTS || echo MISSING'])
exists = r.stdout.strip()
if exists == 'MISSING':
    # Add unmanagedDevices entry
    r = sudo_run(['bash', '-c',
        'echo "" >> /etc/NetworkManager/NetworkManager.conf && '
        'echo "[keyfile]" >> /etc/NetworkManager/NetworkManager.conf && '
        'echo "unmanaged-devices=interface-name:wlan1" >> /etc/NetworkManager/NetworkManager.conf && '
        'echo DONE'])
    print(f'  Added to NM conf: {r.stdout.strip()}')
else:
    print(f'  Already in NM conf')

# Verify wlan1 is unmanaged
time.sleep(2)
r = subprocess.run(['nmcli', 'dev', 'status'], capture_output=True, text=True, timeout=5)
for line in r.stdout.split('\n'):
    if 'wlan1' in line:
        print(f'  wlan1 status: {line.strip()}')

# ===== Step 3: Update LIVI config =====
print()
print('=== Step 3: Update LIVI config ===')
config_path = '/home/raspberry/.config/LIVI/config.json'
with open(config_path) as f:
    cfg = json.load(f)

print(f'  Before: wifiInterface={cfg.get("wifiInterface")}, wirelessAaEnabled={cfg.get("wirelessAaEnabled")}')

cfg['wifiInterface'] = 'wlan1'
cfg['wirelessAaEnabled'] = True

with open(config_path, 'w') as f:
    json.dump(cfg, f, indent=2)

print(f'  After:  wifiInterface=wlan1, wirelessAaEnabled=True')
print(f'  (wifiChannel={cfg.get("wifiChannel")}, wifiType={cfg.get("wifiType")}, wifiPassword={cfg.get("wifiPassword")})')

# ===== Step 4: Restart LIVI =====
print()
print('=== Step 4: Restart LIVI ===')

# Kill any existing hostapd process (might be stale)
r = sudo_run(['bash', '-c', 'pkill -f hostapd 2>/dev/null; echo done'])
print(f'  Killed stale hostapd: {r.stdout.strip()}')

# Restart LIVI
r = subprocess.run(['systemctl', '--user', 'restart', 'livi.service'],
                   capture_output=True, text=True, timeout=10)
print(f'  LIVI restart: rc={r.returncode}')

time.sleep(5)

# Check status
r = subprocess.run(['systemctl', '--user', 'is-active', 'livi.service'],
                   capture_output=True, text=True, timeout=5)
print(f'  LIVI status: {r.stdout.strip()}')

r = subprocess.run(['systemctl', '--user', 'is-active', 'homephone-sidecar.service'],
                   capture_output=True, text=True, timeout=5)
print(f'  Sidecar status: {r.stdout.strip()}')

# ===== Verify: Check if wlan1 is now up and hosting an AP =====
print()
print('=== Verification: wlan1 AP status ===')

# Check wlan1 operstate
try:
    with open('/sys/class/net/wlan1/operstate') as f:
        print(f'  wlan1 operstate: {f.read().strip()}')
except:
    print('  wlan1 operstate: N/A')

# Check if hostapd is running
r = subprocess.run(['pgrep', '-a', 'hostapd'], capture_output=True, text=True, timeout=5)
print(f'  hostapd process: {r.stdout.strip() or "not running"}')

# Check wlan1 IP (AP mode should have an IP)
r = subprocess.run(['ip', 'addr', 'show', 'wlan1'], capture_output=True, text=True, timeout=5)
for line in r.stdout.split('\n'):
    if 'inet ' in line or 'state ' in line or 'mtu' in line:
        print(f'  {line.strip()}')

# Check LIVI logs for wireless AA
print()
print('=== LIVI logs (wireless AA related) ===')
r = subprocess.run(['journalctl', '--user', '-u', 'livi.service', '-n', '30', '--no-pager'],
                   capture_output=True, text=True, timeout=5)
for line in r.stdout.split('\n'):
    if any(x in line.lower() for x in ['wifi', 'wlan', 'ap', 'hotspot', 'wireless', 'aa', 'hostapd', 'error', 'bluetooth']):
        print(f'  {line.strip()}')

# Also check LIVI's own log
print()
print('=== LIVI log file ===')
try:
    with open('/home/raspberry/LIVI/LIVI.log') as f:
        lines = f.readlines()[-30:]
    for line in lines:
        if any(x in line.lower() for x in ['wifi', 'wlan', 'ap', 'hotspot', 'wireless', 'aa', 'hostapd', 'error', 'bt', 'bluetooth']):
            print(f'  {line.strip()}')
except Exception as e:
    print(f'  {e}')

# Check if the AP is visible (scan from wlan0)
print()
print('=== WiFi AP scan (from wlan0, looking for LIVI AP) ===')
r = subprocess.run(['nmcli', 'dev', 'wifi', 'list', 'ifname', 'wlan0'],
                   capture_output=True, text=True, timeout=15)
lines = r.stdout.strip().split('\n')
print(f'  Found {len(lines)-1} networks')
for line in lines:
    if 'homephone' in line.lower() or 'livi' in line.lower() or 'countertop' in line.lower():
        print(f'  MATCH: {line}')
# Show first few
for line in lines[:5]:
    print(f'  {line}')
