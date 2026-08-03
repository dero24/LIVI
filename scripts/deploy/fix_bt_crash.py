#!/usr/bin/env python3
"""Fix: Remove stale phone pairing, disable rogue services, disable wireless AA until dongle is fixed."""
import subprocess, json, os

SUDO_PWD = 'pi\n'
def sudo(cmd, timeout=15):
    return subprocess.run(['sudo', '-S'] + cmd, input=SUDO_PWD,
                         capture_output=True, text=True, timeout=timeout)

PHONE_MAC = '4C:2E:5E:94:9D:3E'

# 1. Remove stale phone pairing from Pi
print('=== 1. Remove stale phone pairing ===')
r = subprocess.run(['bluetoothctl', 'remove', PHONE_MAC],
                   capture_output=True, text=True, timeout=10)
print(f'  Remove {PHONE_MAC}: rc={r.returncode}, {r.stdout.strip() or r.stderr.strip()}')

# Verify it's gone
r = subprocess.run(['bluetoothctl', 'devices'], capture_output=True, text=True, timeout=5)
print(f'  Remaining devices: {r.stdout.strip()}')

# 2. Stop and disable rogue BT services from other agent
print()
print('=== 2. Disable rogue BT services ===')
for svc in ['bluetooth-agent.service', 'bt-autoconnect.service', 'mpris-proxy.service']:
    # Stop
    r = subprocess.run(['systemctl', '--user', 'stop', svc],
                       capture_output=True, text=True, timeout=5)
    print(f'  Stop {svc}: {r.returncode}')
    # Disable
    r = subprocess.run(['systemctl', '--user', 'disable', svc],
                       capture_output=True, text=True, timeout=5)
    print(f'  Disable {svc}: {r.returncode} {r.stdout.strip()}')
    # Check if it exists
    r = subprocess.run(['systemctl', '--user', 'is-enabled', svc],
                       capture_output=True, text=True, timeout=5)
    print(f'  Status: {r.stdout.strip() or r.stderr.strip()}')

# 3. Clear LIVI's lastConnectedAaBtMac and disable autoConn + wireless AA
print()
print('=== 3. Update LIVI config ===')
config_path = '/home/raspberry/.config/LIVI/config.json'
with open(config_path) as f:
    cfg = json.load(f)

print(f'  Before: lastConnectedAaBtMac={cfg.get("lastConnectedAaBtMac")}, autoConn={cfg.get("autoConn")}, wirelessAaEnabled={cfg.get("wirelessAaEnabled")}')

cfg['lastConnectedAaBtMac'] = ''
cfg['autoConn'] = False
cfg['wirelessAaEnabled'] = False  # Disable until dongle driver is fixed

with open(config_path, 'w') as f:
    json.dump(cfg, f, indent=2)

print(f'  After:  lastConnectedAaBtMac="", autoConn=False, wirelessAaEnabled=False')

# 4. Make BT adapter NOT discoverable (no need until dongle is working)
print()
print('=== 4. BT adapter state ===')
r = subprocess.run(['bluetoothctl', 'discoverable', 'off'],
                   capture_output=True, text=True, timeout=5)
print(f'  Discoverable off: rc={r.returncode}')

# 5. Check what the rogue service files contain (for cleanup)
print()
print('=== 5. Rogue service files ===')
for svc in ['bluetooth-agent.service', 'bt-autoconnect.service', 'mpris-proxy.service']:
    path = f'/home/raspberry/.config/systemd/user/{svc}'
    if os.path.exists(path):
        with open(path) as f:
            print(f'  {svc}:')
            for line in f:
                print(f'    {line.rstrip()}')
    else:
        print(f'  {svc}: file not found (may be system-level)')

# 6. Restart LIVI to pick up config changes
print()
print('=== 6. Restart LIVI ===')
r = subprocess.run(['systemctl', '--user', 'restart', 'livi.service'],
                   capture_output=True, text=True, timeout=10)
print(f'  rc={r.returncode}')

import time
time.sleep(10)

r = subprocess.run(['systemctl', '--user', 'is-active', 'livi.service'],
                   capture_output=True, text=True, timeout=5)
print(f'  LIVI: {r.stdout.strip()}')

r = subprocess.run(['systemctl', '--user', 'is-active', 'homephone-sidecar.service'],
                   capture_output=True, text=True, timeout=5)
print(f'  Sidecar: {r.stdout.strip()}')

# 7. Verify no rogue services running
print()
print('=== 7. Verify no rogue BT services ===')
r = subprocess.run(['systemctl', '--user', 'list-units', '--type=service', '--state=active'],
                   capture_output=True, text=True, timeout=5)
for line in r.stdout.split('\n'):
    if any(x in line.lower() for x in ['bt', 'blue', 'mpris', 'livi', 'sidecar']):
        print(f'  {line.strip()}')

# 8. Verify phone is removed
print()
print('=== 8. Final BT state ===')
r = subprocess.run(['bluetoothctl', 'devices'], capture_output=True, text=True, timeout=5)
print(f'  Paired devices: {r.stdout.strip() or "none"}')

r = subprocess.run(['bluetoothctl', 'show'], capture_output=True, text=True, timeout=5)
for line in r.stdout.split('\n'):
    if 'Discoverable' in line or 'Powered' in line or 'Name:' in line:
        print(f'  {line.strip()}')

# 9. Check LIVI helper no longer has wireless AA enabled
print()
print('=== 9. LIVI helper wireless AA ===')
r = subprocess.run(['pgrep', '-f', 'livi-helper'], capture_output=True, text=True, timeout=5)
for pid in r.stdout.strip().split('\n'):
    if not pid:
        continue
    r2 = sudo(['cat', f'/proc/{pid}/environ'], timeout=5)
    has_wireless = 'LIVI_AA_WIRELESS=1' in r2.stdout
    print(f'  PID {pid}: LIVI_AA_WIRELESS=1 = {has_wireless}')

print()
print('=== DONE ===')
print('Phone pairing removed, rogue services disabled, wireless AA disabled.')
print('Pi should be stable now. No auto-connect attempts to phone.')
print('When dongle driver is fixed, re-enable: wirelessAaEnabled=True, autoConn=True')
