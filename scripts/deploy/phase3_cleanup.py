#!/usr/bin/env python3
"""Phase 3: Delete rogue BT scripts, verify sidecar + overlay, clean up."""
import subprocess, os, json

SUDO_PWD = 'pi\n'
def sudo(cmd, timeout=10):
    return subprocess.run(['sudo', '-S'] + cmd, input=SUDO_PWD,
                         capture_output=True, text=True, timeout=timeout)

# 1. Delete rogue BT scripts and service files
print('=== 1. Delete rogue BT scripts ===')
for f in ['/home/raspberry/bt-agent.py', '/home/raspberry/bt_autoconnect.py',
          '/home/raspberry/.config/systemd/user/bluetooth-agent.service',
          '/home/raspberry/.config/systemd/user/bt-autoconnect.service']:
    if os.path.exists(f):
        os.remove(f)
        print(f'  Deleted: {f}')
    else:
        print(f'  Not found: {f}')

# Reload systemd
subprocess.run(['systemctl', '--user', 'daemon-reload'],
               capture_output=True, text=True, timeout=5)
print('  systemd daemon-reload done')

# 2. Verify sidecar is serving the updated settings page
print()
print('=== 2. Sidecar settings page verification ===')
r = subprocess.run(['curl', '-s', 'http://localhost:8123/settings'],
                   capture_output=True, text=True, timeout=5)
checks = [
    ('Wireless Android Auto', 'BT info card'),
    ('Paired Audio Devices', 'Audio devices label'),
    ('in-iframe', 'iframe detection CSS'),
    ('btPollTimer', 'BT polling timer'),
    ('Cache-Control', 'no-store header (check separately)'),
]
for marker, desc in checks:
    found = marker in r.stdout
    print(f'  {"PASS" if found else "FAIL"}: {desc} ({marker})')

# Check no-store header
r2 = subprocess.run(['curl', '-s', '-D', '-', '-o', '/dev/null', 'http://localhost:8123/settings'],
                    capture_output=True, text=True, timeout=5)
has_no_store = 'no-store' in r2.stdout
print(f'  {"PASS" if has_no_store else "FAIL"}: Cache-Control no-store header')

# 3. Verify BT API filters phones
print()
print('=== 3. BT API verification ===')
r = subprocess.run(['curl', '-s', 'http://localhost:8123/api/bluetooth/devices'],
                   capture_output=True, text=True, timeout=5)
try:
    d = json.loads(r.stdout)
    for dev in d.get('devices', []):
        print(f'  {dev["name"]} | is_phone={dev.get("is_phone")} | connected={dev.get("connected")} | icon={dev.get("icon")}')
    adp = d.get('adapter', {})
    print(f'  Adapter: {adp.get("name")} | powered={adp.get("powered")} | discoverable={adp.get("discoverable")}')
except:
    print(f'  Error parsing: {r.stdout[:200]}')

# 4. Verify overlay markers in ASAR
print()
print('=== 4. Overlay ASAR markers ===')
with open('/home/raspberry/LIVI/extracted/resources/app.asar', 'rb') as f:
    asar = f.read().decode('utf-8', 'ignore')
markers = [
    ('homehubOpenSettings', 'Settings overlay function'),
    ('Calibrate Notifications', 'Calibrate button'),
    ('Re-calibrate Apps', 'Re-calibrate button'),
    ('Forget Phone', 'Forget phone button'),
    ('Name Phone', 'Name phone button'),
    ('Loading settings', 'Settings loader'),
    ('retry', 'Retry logic'),
    ('.header{display:none', 'Header hide CSS'),
]
for marker, desc in markers:
    found = marker in asar
    print(f'  {"PASS" if found else "FAIL"}: {desc} ({marker[:30]})')

# 5. Check LIVI config is correct
print()
print('=== 5. LIVI config ===')
with open('/home/raspberry/.config/LIVI/config.json') as f:
    cfg = json.load(f)
print(f'  wirelessAaEnabled: {cfg.get("wirelessAaEnabled")}')
print(f'  autoConn: {cfg.get("autoConn")}')
print(f'  lastConnectedAaBtMac: "{cfg.get("lastConnectedAaBtMac")}"')
print(f'  wifiInterface: {cfg.get("wifiInterface")}')

# 6. Check all active user services
print()
print('=== 6. Active user services ===')
r = subprocess.run(['systemctl', '--user', 'list-units', '--type=service', '--state=active'],
                   capture_output=True, text=True, timeout=5)
for line in r.stdout.split('\n'):
    if any(x in line.lower() for x in ['livi', 'sidecar', 'bt', 'blue', 'hfp', 'mpris']):
        print(f'  {line.strip()}')

# 7. Clean up debug scripts
print()
print('=== 7. Cleanup debug scripts ===')
for f in ['/home/raspberry/quick_check.py', '/home/raspberry/debug_bt_full.py',
          '/home/raspberry/phase2_diagnose.py', '/home/raspberry/fix_bt_crash.py',
          '/home/raspberry/emergency_fix_hang.py', '/home/raspberry/check_syntax.py',
          '/home/raspberry/check_asar.py', '/home/raspberry/check_bt_devices.py',
          '/home/raspberry/find_binaries.py', '/home/raspberry/check_bt.py',
          '/home/raspberry/livi-helper-remote.py', '/home/raspberry/_analyze_aapresence.py']:
    if os.path.exists(f):
        os.remove(f)
        print(f'  Deleted: {f}')
# Don't delete fix_bt_crash.py yet, we might need it
print('  (kept fix_bt_crash.py for reference)')

# 8. Final stability check
print()
print('=== 8. Final state ===')
r = subprocess.run(['systemctl', '--user', 'is-active', 'livi.service'],
                   capture_output=True, text=True, timeout=5)
print(f'  LIVI: {r.stdout.strip()}')
r = subprocess.run(['systemctl', '--user', 'is-active', 'homephone-sidecar.service'],
                   capture_output=True, text=True, timeout=5)
print(f'  Sidecar: {r.stdout.strip()}')
r = subprocess.run(['bluetoothctl', 'devices'], capture_output=True, text=True, timeout=5)
print(f'  BT devices: {r.stdout.strip()}')
r = subprocess.run(['cat', '/sys/module/usbcore/parameters/autosuspend'],
                   capture_output=True, text=True, timeout=5)
print(f'  USB autosuspend: {r.stdout.strip()}')
r = subprocess.run(['/usr/sbin/iw', 'dev', 'wlan0', 'get', 'power_save'],
                   capture_output=True, text=True, timeout=5)
print(f'  wlan0 power_save: {r.stdout.strip()}')
